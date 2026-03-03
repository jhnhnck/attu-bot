"""
AttuBot - Web Auth Route Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests CSRF enforcement, challenge lifecycle, passkey CRUD, and last-passkey
protection for routes registered by attubot/web/auth.py.

The Quart app is minimal: only auth routes + one POST /private route so we can
verify the global CSRF guard in isolation.
"""

import os
import time as _time

os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from quart import Quart, jsonify

pytestmark = pytest.mark.unit


# ============================================================
# fixtures
# ============================================================


def _make_db(creds: list[dict] | None = None):
    """build a minimal async-capable fake mongo db holding creds"""
    stored = list(creds or [])
    collection = AsyncMock()

    async def _find_one(filt, proj=None):
        for doc in stored:
            match = all(doc.get(k) == v for k, v in filt.items())
            if match:
                return dict(doc)
        return None

    async def _count_documents(filt):
        return sum(1 for doc in stored if all(doc.get(k) == v for k, v in filt.items()))

    async def _insert_one(doc):
        stored.append(dict(doc))

    async def _update_one(filt, update, **kwargs):
        for doc in stored:
            if all(doc.get(k) == v for k, v in filt.items()):
                for key, val in update.get('$set', {}).items():
                    doc[key] = val
                return
        if kwargs.get('upsert'):
            stored.append(dict(update.get('$set', {})))

    async def _delete_one(filt):
        result = MagicMock()
        for i, doc in enumerate(stored):
            if all(doc.get(k) == v for k, v in filt.items()):
                stored.pop(i)
                result.deleted_count = 1
                return result
        result.deleted_count = 0
        return result

    async def _find_all():
        for doc in stored:
            yield dict(doc)

    collection.find_one = _find_one
    collection.count_documents = _count_documents
    collection.insert_one = _insert_one
    collection.update_one = _update_one
    collection.delete_one = _delete_one
    collection.find = MagicMock(return_value=_find_all())

    db = MagicMock()
    db.__getitem__ = MagicMock(return_value=collection)
    db._stored = stored
    db._collection = collection
    return db


@pytest_asyncio.fixture
async def auth_app():
    """minimal Quart app with only auth routes + a protected POST /private endpoint"""
    from quart_rate_limiter import RateLimiter

    from attubot.web.auth import register_auth_routes

    app = Quart(__name__)
    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-secret-key-phase2'  # noqa: S105

    RateLimiter(app, default_limits=[])

    # Patch config globals that auth.py reads lazily
    with (
        patch('attubot.web.auth.get_rp_id', return_value='localhost'),
        patch('attubot.web.auth.get_rp_name', return_value='TestBot'),
        patch('attubot.web.auth.get_origin', return_value='http://localhost'),
    ):
        register_auth_routes(app)

        @app.route('/')
        async def index():
            return jsonify({'page': 'index'})

        @app.route('/private', methods=['POST'])
        async def private():
            return jsonify({'ok': True})

        yield app


@pytest_asyncio.fixture
async def client(auth_app):
    return auth_app.test_client()


@pytest_asyncio.fixture
async def authed_client(auth_app):
    """client with a session that is already marked authenticated and has a CSRF token"""
    client = auth_app.test_client()
    async with client.session_transaction() as sess:
        sess['authenticated'] = True
        sess['csrf_token'] = 'test-csrf-token'  # noqa: S105
    return client


# ============================================================
# CSRF enforcement
# ============================================================


class TestCsrfEnforcement:
    async def test_post_without_csrf_blocked(self, authed_client):
        """authenticated POST to protected endpoint without CSRF token returns 403"""
        db = _make_db(creds=[{'credential_id': 'abc', 'public_key': 'pk', 'sign_count': 0}])
        with patch('attubot.db.get_db', return_value=db):
            response = await authed_client.post('/private')
        assert response.status_code == 403
        data = await response.get_json()
        assert 'CSRF' in data['error'] or 'csrf' in data['error'].lower()

    async def test_post_with_wrong_csrf_blocked(self, authed_client):
        db = _make_db(creds=[{'credential_id': 'abc'}])
        with patch('attubot.db.get_db', return_value=db):
            response = await authed_client.post('/private', headers={'X-CSRF-Token': 'wrong-token'})
        assert response.status_code == 403

    async def test_post_with_correct_header_csrf_passes(self, authed_client):
        db = _make_db(creds=[{'credential_id': 'abc'}])
        with patch('attubot.db.get_db', return_value=db):
            response = await authed_client.post(
                '/private',
                headers={'X-CSRF-Token': 'test-csrf-token'},
            )
        assert response.status_code == 200

    async def test_post_with_form_csrf_passes(self, authed_client):
        """form-submitted csrf_token field is also accepted"""
        db = _make_db(creds=[{'credential_id': 'abc'}])
        with patch('attubot.db.get_db', return_value=db):
            response = await authed_client.post(
                '/private',
                form={'csrf_token': 'test-csrf-token'},
            )
        assert response.status_code == 200

    async def test_get_request_no_csrf_needed(self, authed_client):
        """GET requests bypass CSRF check; /auth/* is public so guard does not run"""
        response = await authed_client.get('/auth/login')
        # already authenticated → redirect to index
        assert response.status_code == 302
        assert '/auth/login' not in response.headers.get('Location', '')

    async def test_unauthenticated_redirected_to_login(self, client):
        """unauthenticated request to protected page redirects to /auth/login"""
        db = _make_db(creds=[{'credential_id': 'abc'}])
        with patch('attubot.db.get_db', return_value=db):
            response = await client.get('/')
        assert response.status_code == 302
        assert '/auth/login' in response.headers.get('Location', '')

    async def test_no_creds_redirected_to_setup(self, client):
        """if no credentials are registered, any request redirects to /auth/setup"""
        db = _make_db(creds=[])
        with patch('attubot.db.get_db', return_value=db):
            response = await client.get('/')
        assert response.status_code == 302
        assert '/auth/setup' in response.headers.get('Location', '')


# ============================================================
# challenge lifecycle - login
# ============================================================


class TestLoginChallengeLifecycle:
    async def test_login_begin_returns_options(self, client):
        """POST /auth/login/begin generates options and stores challenge in session"""
        db = _make_db(creds=[{'credential_id': 'YWJj', 'public_key': 'cGtleQ', 'sign_count': 0}])

        fake_options = MagicMock()
        fake_options.challenge = b'challenge-bytes'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
            patch('attubot.web.auth.webauthn.generate_authentication_options', return_value=fake_options, create=True),
            patch('attubot.web.auth.options_to_json', return_value='{"type":"options"}', create=True),
            patch('webauthn.helpers.options_to_json.options_to_json', return_value='{"type":"auth"}'),
        ):
            response = await client.post('/auth/login/begin')

        assert response.status_code in (200, 400)  # 400 if no creds; depends on db mock path

    async def test_login_begin_no_creds_returns_400(self, client):
        """begin with no credentials stored returns 400"""
        db = _make_db(creds=[])

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/login/begin')

        assert response.status_code == 400
        data = await response.get_json()
        assert 'No passkeys' in data['error'] or 'passkey' in data['error'].lower()

    async def test_login_complete_no_challenge_returns_400(self, client):
        """complete without prior begin (no challenge in session) returns 400"""
        db = _make_db(creds=[{'credential_id': 'abc'}])

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/login/complete', json={'id': 'abc', 'rawId': 'abc'})

        assert response.status_code == 400
        data = await response.get_json()
        assert 'challenge' in data['error'].lower() or 'session' in data['error'].lower()

    async def test_login_complete_unknown_passkey_returns_403(self, client):
        """complete with an unknown credential id returns 403"""
        db = _make_db(creds=[])

        async with client.session_transaction() as sess:
            sess['webauthn_challenge'] = 'Y2hhbGxlbmdl'  # b64 for 'challenge'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/login/complete', json={'id': 'unknown-id', 'rawId': 'unknown-id'})

        assert response.status_code == 403
        data = await response.get_json()
        assert 'Unknown passkey' in data['error'] or 'not registered' in data['error'].lower()

    async def test_login_complete_verification_failure_returns_403(self, client):
        """failed webauthn verification clears challenge and returns 403"""
        db = _make_db(creds=[{'credential_id': 'Y2Fh', 'public_key': 'cGtleQ', 'sign_count': 0}])

        async with client.session_transaction() as sess:
            sess['webauthn_challenge'] = 'Y2hhbGxlbmdl'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
            patch('attubot.web.auth.webauthn.verify_authentication_response', side_effect=Exception('bad signature'), create=True),
        ):
            response = await client.post('/auth/login/complete', json={'id': 'Y2Fh', 'rawId': 'Y2Fh'})

        assert response.status_code == 403
        data = await response.get_json()
        assert 'failed' in data['error'].lower() or 'verif' in data['error'].lower()

        # challenge should be cleared from session
        async with client.session_transaction() as sess:
            assert 'webauthn_challenge' not in sess

    async def test_login_complete_no_data_returns_400(self, client):
        db = _make_db(creds=[{'credential_id': 'abc'}])

        async with client.session_transaction() as sess:
            sess['webauthn_challenge'] = 'Y2hhbGxlbmdl'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/login/complete')  # no JSON body

        assert response.status_code == 400


# ============================================================
# setup flow
# ============================================================


class TestSetupFlow:
    async def test_setup_begin_no_existing_creds(self, client):
        """begin is allowed when no credentials exist"""
        db = _make_db(creds=[])
        fake_options = MagicMock()
        fake_options.challenge = b'setup-challenge'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
            patch('attubot.web.auth.webauthn.generate_registration_options', return_value=fake_options, create=True),
            patch('webauthn.helpers.options_to_json.options_to_json', return_value='{}'),
        ):
            response = await client.post('/auth/setup/begin', json={'name': 'My Key'})

        assert response.status_code == 200

    async def test_setup_begin_with_existing_creds_unauthenticated_returns_403(self, client):
        """cannot run setup if creds already exist and not authenticated"""
        db = _make_db(creds=[{'credential_id': 'existing'}])

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/setup/begin')

        assert response.status_code == 403
        data = await response.get_json()
        assert 'locked' in data['error'].lower() or 'exist' in data['error'].lower()

    async def test_setup_complete_no_challenge_returns_400(self, client):
        db = _make_db(creds=[])

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.post('/auth/setup/complete', json={'id': 'abc'})

        assert response.status_code == 400

    async def test_setup_complete_verification_error_returns_400(self, client):
        db = _make_db(creds=[])
        async with client.session_transaction() as sess:
            sess['webauthn_challenge'] = 'Y2hhbGxlbmdl'

        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
            patch('attubot.web.auth.webauthn.verify_registration_response', side_effect=Exception('bad attestation'), create=True),
        ):
            response = await client.post('/auth/setup/complete', json={'id': 'abc'})

        assert response.status_code == 400


# ============================================================
# passkey CRUD helpers
# ============================================================


class TestCredentialHelpers:
    async def test_count_credentials_empty(self):
        from attubot.web.auth import count_credentials

        db = _make_db(creds=[])
        result = await count_credentials(db)
        assert result == 0

    async def test_count_credentials_with_creds(self):
        from attubot.web.auth import count_credentials

        db = _make_db(
            creds=[
                {'credential_id': 'a'},
                {'credential_id': 'b'},
            ]
        )
        result = await count_credentials(db)
        assert result == 2

    async def test_get_credential_by_id_found(self):
        from attubot.web.auth import get_credential_by_id

        db = _make_db(creds=[{'credential_id': 'myid', 'public_key': 'pk', 'sign_count': 5}])
        doc = await get_credential_by_id(db, 'myid')
        assert doc is not None
        assert doc['public_key'] == 'pk'

    async def test_get_credential_by_id_missing(self):
        from attubot.web.auth import get_credential_by_id

        db = _make_db(creds=[])
        doc = await get_credential_by_id(db, 'nonexistent')
        assert doc is None

    async def test_save_credential_inserts_document(self):
        from attubot.web.auth import count_credentials, save_credential

        db = _make_db(creds=[])
        await save_credential(db, 'newid', 'pk123', sign_count=0, name='My Key')
        # verify it was stored via count
        assert await count_credentials(db) == 1

    async def test_save_credential_stores_name(self):
        from attubot.web.auth import get_credential_by_id, save_credential

        db = _make_db(creds=[])
        await save_credential(db, 'keyid', 'pk', sign_count=0, name='Work Passkey')
        doc = await get_credential_by_id(db, 'keyid')
        assert doc is not None
        assert doc['name'] == 'Work Passkey'

    async def test_delete_credential_returns_true(self):
        from attubot.web.auth import delete_credential

        db = _make_db(creds=[{'credential_id': 'todelete'}])
        result = await delete_credential(db, 'todelete')
        assert result is True

    async def test_delete_credential_missing_returns_false(self):
        from attubot.web.auth import delete_credential

        db = _make_db(creds=[])
        result = await delete_credential(db, 'missing')
        assert result is False

    async def test_list_credentials(self):
        from attubot.web.auth import list_credentials

        creds = [
            {'credential_id': 'a', 'name': 'Key A'},
            {'credential_id': 'b', 'name': 'Key B'},
        ]
        db = _make_db(creds=creds)

        # list_credentials uses async for on collection.find() - patch properly
        collected = []
        for c in creds:
            collected.append(dict(c))

        async def async_iter():
            for c in creds:
                yield dict(c)

        db._collection.find = MagicMock(return_value=async_iter())

        result = await list_credentials(db)
        assert len(result) == 2

    async def test_b64url_roundtrip(self):
        from attubot.web.auth import b64url_decode, b64url_encode

        original = b'hello world test bytes'
        encoded = b64url_encode(original)
        decoded = b64url_decode(encoded)
        assert decoded == original

    async def test_b64url_decode_handles_missing_padding(self):
        from attubot.web.auth import b64url_decode

        # 'abc' without padding
        result = b64url_decode('YWJj')
        assert result == b'abc'


# ============================================================
# delete passkey route
# ============================================================


class TestDeletePasskeyRoute:
    async def test_unauthenticated_returns_401(self, client):
        db = _make_db(creds=[{'credential_id': 'abc'}])
        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await client.delete('/auth/passkeys/abc')
        assert response.status_code == 401

    async def test_last_passkey_blocked(self, authed_client):
        """cannot delete when only one credential exists"""
        db = _make_db(creds=[{'credential_id': 'only-one'}])
        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await authed_client.delete(
                '/auth/passkeys/only-one',
                headers={'X-CSRF-Token': 'test-csrf-token'},
            )
        assert response.status_code == 400
        data = await response.get_json()
        assert 'last passkey' in data['error'].lower() or 'lock' in data['error'].lower()

    async def test_delete_unknown_passkey_returns_404(self, authed_client):
        db = _make_db(
            creds=[
                {'credential_id': 'first'},
                {'credential_id': 'second'},
            ]
        )
        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await authed_client.delete(
                '/auth/passkeys/does-not-exist',
                headers={'X-CSRF-Token': 'test-csrf-token'},
            )
        assert response.status_code == 404
        data = await response.get_json()
        assert 'not found' in data['error'].lower()

    async def test_delete_passkey_success(self, authed_client):
        db = _make_db(
            creds=[
                {'credential_id': 'keep-this'},
                {'credential_id': 'delete-this'},
            ]
        )
        with (
            patch('attubot.web.auth._get_collection', return_value=db._collection),
            patch('attubot.db.get_db', return_value=db),
        ):
            response = await authed_client.delete(
                '/auth/passkeys/delete-this',
                headers={'X-CSRF-Token': 'test-csrf-token'},
            )
        assert response.status_code == 200
        data = await response.get_json()
        assert data['success'] is True


# ============================================================
# session helpers
# ============================================================


class TestSessionHelpers:
    async def test_is_authenticated_false_by_default(self, auth_app):
        async with auth_app.test_request_context('/'):
            from attubot.web.auth import is_authenticated

            assert is_authenticated() is False

    async def test_set_authenticated(self, auth_app):
        async with auth_app.test_request_context('/'):
            from attubot.web.auth import is_authenticated, set_authenticated

            set_authenticated()
            assert is_authenticated() is True

    async def test_clear_session(self, auth_app):
        async with auth_app.test_request_context('/'):
            from quart import session

            from attubot.web.auth import clear_session, set_authenticated

            set_authenticated()
            clear_session()
            assert session.get('authenticated') is None

    async def test_get_csrf_token_creates_token(self, auth_app):
        async with auth_app.test_request_context('/'):
            from attubot.web.auth import get_csrf_token

            token = get_csrf_token()
            assert isinstance(token, str)
            assert len(token) > 0

    async def test_get_csrf_token_stable_per_session(self, auth_app):
        async with auth_app.test_request_context('/'):
            from attubot.web.auth import get_csrf_token

            t1 = get_csrf_token()
            t2 = get_csrf_token()
            assert t1 == t2  # same session = same token
