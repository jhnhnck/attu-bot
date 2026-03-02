"""
AttuBot - WebAuthn Passkey Authentication
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from datetime import timedelta
from functools import wraps

import webauthn
from quart import jsonify, redirect, render_template, request, session, url_for
from quart_rate_limiter import rate_limit
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from attubot.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------


def get_rp_id() -> str:
    from attubot.web.app import config

    return config.webauthn.rp_id


def get_rp_name() -> str:
    from attubot.web.app import config

    return config.webauthn.rp_name


def get_origin() -> str:
    from attubot.web.app import config

    return config.webauthn.origin


# ---------------------------------------------------------------------------
# MongoDB credential helpers
# ---------------------------------------------------------------------------


def _get_collection(db):
    return db['webauthn_credentials']


async def count_credentials(db) -> int:
    """Return total number of registered passkeys."""
    return await _get_collection(db).count_documents({})


async def list_credentials(db) -> list[dict]:
    """Return all credentials (for display)."""
    creds = []
    async for doc in _get_collection(db).find({}, {'_id': 0}):
        creds.append(doc)
    return creds


async def get_credential_by_id(db, credential_id_b64: str) -> dict | None:
    """Fetch a single credential by base64url-encoded ID."""
    return await _get_collection(db).find_one({'credential_id': credential_id_b64}, {'_id': 0})


async def save_credential(db, credential_id_b64: str, public_key_b64: str, sign_count: int, name: str = 'Passkey'):
    """Insert a new credential."""
    await _get_collection(db).insert_one({
        'credential_id': credential_id_b64,
        'public_key': public_key_b64,
        'sign_count': sign_count,
        'name': name,
        'created_at': int(time.time()),
        'last_used': int(time.time()),
    })
    logger.info(f'Passkey registered: {name}')


async def update_sign_count(db, credential_id_b64: str, new_count: int):
    """Update the stored sign count and last_used timestamp after successful auth."""
    await _get_collection(db).update_one(
        {'credential_id': credential_id_b64},
        {'$set': {'sign_count': new_count, 'last_used': int(time.time())}},
    )


async def delete_credential(db, credential_id_b64: str) -> bool:
    """Delete a credential. Returns True if deleted."""
    result = await _get_collection(db).delete_one({'credential_id': credential_id_b64})
    return result.deleted_count > 0


# ---------------------------------------------------------------------------
# Base64url utilities
# ---------------------------------------------------------------------------


def b64url_encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def b64url_decode(s: str) -> bytes:
    # Add padding
    padding = 4 - len(s) % 4
    if padding != 4:
        s += '=' * padding
    return urlsafe_b64decode(s)


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------

SESSION_KEY = 'authenticated'
CHALLENGE_KEY = 'webauthn_challenge'


def get_csrf_token() -> str:
    """Get or create the per-session CSRF token (L3)."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
    return session['csrf_token']


def is_authenticated() -> bool:
    return session.get(SESSION_KEY) is True


def set_authenticated():
    session[SESSION_KEY] = True
    session.permanent = True


def clear_session():
    session.clear()


# ---------------------------------------------------------------------------
# login_required decorator
# ---------------------------------------------------------------------------


def login_required(f):
    @wraps(f)
    async def decorated(*args, **kwargs):
        if not is_authenticated():
            # Store the original URL so we can redirect back after login
            next_url = request.url
            return redirect(url_for('auth_login') + f'?next={next_url}')
        return await f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register_auth_routes(app):  # noqa: PLR0915
    """Register all /auth/* routes and the before_request guard."""

    @app.before_request
    async def require_auth():
        """Global auth guard — runs before every request."""
        # Paths that are always public
        public_prefixes = ('/auth/', '/static/', '/health')
        path = request.path

        if any(path.startswith(p) for p in public_prefixes):
            return  # allow through

        db = None
        try:
            from attubot import db as db_module

            db = db_module.get_db()
        except Exception:
            # DB not ready yet — let it through so startup can proceed
            return

        # If no credentials exist, force setup
        n = await count_credentials(db)
        if n == 0:
            if path != '/auth/setup':
                return redirect(url_for('auth_setup'))
            return  # let the setup page render

        # Credentials exist — require a valid session
        if not is_authenticated():
            next_url = request.url
            return redirect(url_for('auth_login') + f'?next={next_url}')

        # CSRF protection for all state-changing requests (L3).
        # Tokens are accepted from the X-CSRF-Token header (JSON API) or a
        # hidden form field named csrf_token (HTML form submissions, e.g. logout).
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = request.headers.get('X-CSRF-Token')
            if not token:
                form_data = await request.form
                token = form_data.get('csrf_token')
            if not token or token != session.get('csrf_token'):
                return jsonify({'error': 'CSRF token invalid or missing'}), 403

    # ---- Login page --------------------------------------------------------

    @app.route('/auth/login')
    async def auth_login():
        if is_authenticated():
            return redirect(url_for('index'))
        return await render_template('login.html', title='Sign In')

    # ---- Login begin (generate challenge) ----------------------------------

    @app.route('/auth/login/begin', methods=['POST'])
    @rate_limit(10, timedelta(minutes=1))
    async def auth_login_begin():
        from attubot import db as db_module

        db = db_module.get_db()

        creds = await list_credentials(db)
        if not creds:
            return jsonify({'error': 'No passkeys registered — please run setup'}), 400

        allow_credentials = [PublicKeyCredentialDescriptor(id=b64url_decode(c['credential_id'])) for c in creds]

        options = webauthn.generate_authentication_options(
            rp_id=get_rp_id(),
            allow_credentials=allow_credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )

        # Store challenge in session for verification
        session[CHALLENGE_KEY] = b64url_encode(options.challenge)

        from webauthn.helpers.options_to_json import options_to_json

        return app.response_class(
            options_to_json(options),
            content_type='application/json',
        )

    # ---- Login complete (verify assertion) ---------------------------------

    @app.route('/auth/login/complete', methods=['POST'])
    @rate_limit(10, timedelta(minutes=1))
    async def auth_login_complete():
        from attubot import db as db_module

        db = db_module.get_db()

        challenge_b64 = session.get(CHALLENGE_KEY)
        if not challenge_b64:
            return jsonify({'error': 'No challenge in session — restart login'}), 400

        data = await request.get_json()
        if not data:
            return jsonify({'error': 'No credential data provided'}), 400

        try:
            # Find the credential by ID
            raw_id = data.get('rawId') or data.get('id')
            if not raw_id:
                return jsonify({'error': 'Missing credential ID'}), 400

            cred_doc = await get_credential_by_id(db, raw_id)
            if not cred_doc:
                return jsonify({'error': 'Unknown passkey — not registered on this server'}), 403

            import json as _json

            credential_json = _json.dumps(data)

            verification = webauthn.verify_authentication_response(
                credential=credential_json,
                expected_challenge=b64url_decode(challenge_b64),
                expected_rp_id=get_rp_id(),
                expected_origin=get_origin(),
                credential_public_key=b64url_decode(cred_doc['public_key']),
                credential_current_sign_count=cred_doc['sign_count'],
                require_user_verification=False,
            )

            # Update sign count
            await update_sign_count(db, raw_id, verification.new_sign_count)

            # Clear the challenge
            session.pop(CHALLENGE_KEY, None)

            # Mark session as authenticated
            set_authenticated()

            logger.info(f'Successful passkey login from {request.remote_addr}')
            return jsonify({'success': True})

        except Exception as e:
            logger.warn(f'Passkey login failed from {request.remote_addr}: {e}')
            session.pop(CHALLENGE_KEY, None)
            return jsonify({'error': 'Passkey verification failed'}), 403

    # ---- Logout ------------------------------------------------------------

    @app.route('/auth/logout', methods=['POST'])
    async def auth_logout():
        clear_session()
        return redirect(url_for('auth_login'))

    # ---- Setup page (only when no creds exist) -----------------------------

    @app.route('/auth/setup')
    async def auth_setup():
        from attubot import db as db_module

        try:
            db = db_module.get_db()
            n = await count_credentials(db)
            if n > 0 and not is_authenticated():
                return redirect(url_for('auth_login'))
        except Exception:
            logger.debug('DB not available during setup page load — rendering setup anyway')
        return await render_template('setup.html', title='Initial Setup — Register Passkey')

    # ---- Setup begin (generate registration challenge) --------------------

    @app.route('/auth/setup/begin', methods=['POST'])
    async def auth_setup_begin():
        from attubot import db as db_module

        db = db_module.get_db()

        # Only allow setup when no credentials exist OR already authenticated
        n = await count_credentials(db)
        if n > 0 and not is_authenticated():
            return jsonify({'error': 'Setup is locked — passkeys already exist'}), 403

        body = await request.get_json() or {}
        name = body.get('name', 'Passkey')

        options = webauthn.generate_registration_options(
            rp_id=get_rp_id(),
            rp_name=get_rp_name(),
            user_id=b'attubot-admin',
            user_name='admin',
            user_display_name='AttuBot Admin',
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )

        session[CHALLENGE_KEY] = b64url_encode(options.challenge)
        session['pending_passkey_name'] = name

        from webauthn.helpers.options_to_json import options_to_json

        return app.response_class(
            options_to_json(options),
            content_type='application/json',
        )

    # ---- Setup complete (verify + store) -----------------------------------

    @app.route('/auth/setup/complete', methods=['POST'])
    @rate_limit(10, timedelta(minutes=1))
    async def auth_setup_complete():
        from attubot import db as db_module

        db = db_module.get_db()

        n = await count_credentials(db)
        if n > 0 and not is_authenticated():
            return jsonify({'error': 'Setup is locked — passkeys already exist'}), 403

        challenge_b64 = session.get(CHALLENGE_KEY)
        if not challenge_b64:
            return jsonify({'error': 'No challenge in session — restart setup'}), 400

        data = await request.get_json()
        if not data:
            return jsonify({'error': 'No credential data provided'}), 400

        try:
            import json as _json

            credential_json = _json.dumps(data)

            verification = webauthn.verify_registration_response(
                credential=credential_json,
                expected_challenge=b64url_decode(challenge_b64),
                expected_rp_id=get_rp_id(),
                expected_origin=get_origin(),
                require_user_verification=False,
            )

            cred_id_b64 = b64url_encode(verification.credential_id)
            pub_key_b64 = b64url_encode(verification.credential_public_key)
            name = session.pop('pending_passkey_name', 'Passkey')

            await save_credential(db, cred_id_b64, pub_key_b64, verification.sign_count, name)

            session.pop(CHALLENGE_KEY, None)
            set_authenticated()

            logger.info(f'Passkey registered via setup from {request.remote_addr}: {name}')
            return jsonify({'success': True, 'message': f'Passkey "{name}" registered successfully'})

        except Exception as e:
            logger.warn(f'Passkey setup failed from {request.remote_addr}: {e}')
            session.pop(CHALLENGE_KEY, None)
            return jsonify({'error': f'Passkey registration failed: {e}'}), 400

    # ---- Passkey management page (authenticated) ---------------------------

    @app.route('/auth/passkeys')
    async def auth_passkeys():
        if not is_authenticated():
            return redirect(url_for('auth_login'))
        from attubot import db as db_module

        db = db_module.get_db()
        creds = await list_credentials(db)
        return await render_template('passkeys.html', title='Manage Passkeys', passkeys=creds)

    # ---- Register additional passkey begin ---------------------------------

    @app.route('/auth/register/begin', methods=['POST'])
    async def auth_register_begin():
        if not is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        body = await request.get_json() or {}
        name = body.get('name', 'Passkey')

        options = webauthn.generate_registration_options(
            rp_id=get_rp_id(),
            rp_name=get_rp_name(),
            user_id=b'attubot-admin',
            user_name='admin',
            user_display_name='AttuBot Admin',
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
        )

        session[CHALLENGE_KEY] = b64url_encode(options.challenge)
        session['pending_passkey_name'] = name

        from webauthn.helpers.options_to_json import options_to_json

        return app.response_class(
            options_to_json(options),
            content_type='application/json',
        )

    # ---- Register additional passkey complete ------------------------------

    @app.route('/auth/register/complete', methods=['POST'])
    @rate_limit(10, timedelta(minutes=1))
    async def auth_register_complete():
        if not is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        from attubot import db as db_module

        db = db_module.get_db()

        challenge_b64 = session.get(CHALLENGE_KEY)
        if not challenge_b64:
            return jsonify({'error': 'No challenge in session'}), 400

        data = await request.get_json()
        if not data:
            return jsonify({'error': 'No credential data provided'}), 400

        try:
            import json as _json

            credential_json = _json.dumps(data)

            verification = webauthn.verify_registration_response(
                credential=credential_json,
                expected_challenge=b64url_decode(challenge_b64),
                expected_rp_id=get_rp_id(),
                expected_origin=get_origin(),
                require_user_verification=False,
            )

            cred_id_b64 = b64url_encode(verification.credential_id)
            pub_key_b64 = b64url_encode(verification.credential_public_key)
            name = session.pop('pending_passkey_name', 'Passkey')

            await save_credential(db, cred_id_b64, pub_key_b64, verification.sign_count, name)
            session.pop(CHALLENGE_KEY, None)

            logger.info(f'Additional passkey registered from {request.remote_addr}: {name}')
            return jsonify({'success': True, 'message': f'Passkey "{name}" registered successfully'})

        except Exception as e:
            logger.warn(f'Passkey registration failed from {request.remote_addr}: {e}')
            session.pop(CHALLENGE_KEY, None)
            return jsonify({'error': f'Passkey registration failed: {e}'}), 400

    # ---- Delete passkey ----------------------------------------------------

    @app.route('/auth/passkeys/<credential_id>', methods=['DELETE'])
    async def auth_delete_passkey(credential_id: str):
        if not is_authenticated():
            return jsonify({'error': 'Not authenticated'}), 401

        from attubot import db as db_module

        db = db_module.get_db()

        # Safety: don't allow deleting the last passkey
        n = await count_credentials(db)
        if n <= 1:
            return jsonify({'error': 'Cannot delete the last passkey — you would lock yourself out'}), 400

        deleted = await delete_credential(db, credential_id)
        if not deleted:
            return jsonify({'error': 'Passkey not found'}), 404

        logger.info(f'Passkey deleted from {request.remote_addr}: {credential_id[:16]}...')
        return jsonify({'success': True, 'message': 'Passkey deleted'})

    logger.info('Auth routes registered')
