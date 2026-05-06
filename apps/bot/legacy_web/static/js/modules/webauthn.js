/**
 * WebAuthn / Passkey client-side helpers
 *
 * Two exported functions:
 *   beginAuthentication() — sign-in flow
 *   beginRegistration(name, beginUrl, completeUrl) — registration flow
 *
 * Both handle base64url encoding/decoding needed to bridge the JSON
 * representation used by py-webauthn with the ArrayBuffer types the
 * browser's PublicKeyCredential API requires.
 */

// ---------------------------------------------------------------------------
// Base64url helpers
// ---------------------------------------------------------------------------

function b64urlToBytes(b64url) {
    // Pad to a multiple of 4
    const padded = b64url.replace(/-/g, '+').replace(/_/g, '/');
    const padding = '='.repeat((4 - (padded.length % 4)) % 4);
    const binary = atob(padded + padding);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes.buffer;
}

function bytesToB64url(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (const b of bytes) {
        binary += String.fromCharCode(b);
    }
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=/g, '');
}

// ---------------------------------------------------------------------------
// Transform server options → browser API format
// ---------------------------------------------------------------------------

/**
 * Converts py-webauthn's JSON authentication options so the browser can use them.
 * Decodes base64url challenge and allowCredentials IDs to ArrayBuffers.
 */
function decodeAuthenticationOptions(opts) {
    return {
        ...opts,
        challenge: b64urlToBytes(opts.challenge),
        allowCredentials: (opts.allowCredentials || []).map((cred) => ({
            ...cred,
            id: b64urlToBytes(cred.id),
        })),
        timeout: opts.timeout ?? 60000,
    };
}

/**
 * Converts py-webauthn's JSON registration options so the browser can use them.
 * Decodes base64url challenge and user.id to ArrayBuffers.
 * Also decodes excludeCredentials IDs if present.
 */
function decodeRegistrationOptions(opts) {
    return {
        ...opts,
        challenge: b64urlToBytes(opts.challenge),
        user: {
            ...opts.user,
            id: b64urlToBytes(opts.user.id),
        },
        excludeCredentials: (opts.excludeCredentials || []).map((cred) => ({
            ...cred,
            id: b64urlToBytes(cred.id),
        })),
        timeout: opts.timeout ?? 60000,
    };
}

// ---------------------------------------------------------------------------
// Transform browser credential → JSON for server
// ---------------------------------------------------------------------------

/**
 * Encodes a PublicKeyCredential (authentication assertion) to plain JSON.
 */
function encodeAssertion(credential) {
    const {response} = credential;
    return {
        id: credential.id,
        rawId: bytesToB64url(credential.rawId),
        type: credential.type,
        response: {
            authenticatorData: bytesToB64url(response.authenticatorData),
            clientDataJSON: bytesToB64url(response.clientDataJSON),
            signature: bytesToB64url(response.signature),
            userHandle: response.userHandle
                ? bytesToB64url(response.userHandle)
                : null,
        },
    };
}

/**
 * Encodes a PublicKeyCredential (registration attestation) to plain JSON.
 */
function encodeAttestation(credential) {
    const {response} = credential;
    return {
        id: credential.id,
        rawId: bytesToB64url(credential.rawId),
        type: credential.type,
        response: {
            attestationObject: bytesToB64url(response.attestationObject),
            clientDataJSON: bytesToB64url(response.clientDataJSON),
        },
    };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Run the full passkey sign-in flow.
 *
 * 1. POST /auth/login/begin  → get options from server
 * 2. navigator.credentials.get() → browser shows passkey prompt
 * 3. POST /auth/login/complete → server verifies, sets session
 *
 * Throws on any failure so callers can catch and display errors.
 */
export async function beginAuthentication() {
    if (!window.PublicKeyCredential) {
        throw new Error(
            'Your browser does not support passkeys. Please use a modern browser.',
        );
    }

    // Step 1: get challenge from server
    const beginRes = await fetch('/auth/login/begin', { method: 'POST' });
    if (!beginRes.ok) {
        const err = await beginRes.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to start authentication');
    }
    const options = await beginRes.json();

    // Step 2: browser passkey prompt
    let credential;
    try {
        credential = await navigator.credentials.get({
            publicKey: decodeAuthenticationOptions(options),
        });
    } catch (err) {
        if (err.name === 'NotAllowedError') {
            throw new Error('Passkey prompt was dismissed or timed out', { cause: err });
        }
        throw new Error(`Passkey error: ${err.message}`, { cause: err });
    }

    if (!credential) {
        throw new Error('No credential returned from authenticator');
    }

    // Step 3: send assertion to server for verification
    const completeRes = await fetch('/auth/login/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(encodeAssertion(credential)),
    });

    const result = await completeRes.json().catch(() => ({}));
    if (!completeRes.ok) {
        throw new Error(result.error || 'Passkey verification failed');
    }

    return result;
}

/**
 * Run the full passkey registration flow.
 *
 * @param {string} name - Friendly label for the new passkey
 * @param {string} beginUrl - Server endpoint to get registration options (e.g. /auth/setup/begin)
 * @param {string} completeUrl - Server endpoint to verify registration (e.g. /auth/setup/complete)
 *
 * Throws on any failure.
 */
export async function beginRegistration(
    name,
    beginUrl = '/auth/register/begin',
    completeUrl = '/auth/register/complete',
) {
    if (!window.PublicKeyCredential) {
        throw new Error(
            'Your browser does not support passkeys. Please use a modern browser.',
        );
    }

    // Step 1: get registration options from server
    const beginRes = await fetch(beginUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });

    if (!beginRes.ok) {
        const err = await beginRes.json().catch(() => ({}));
        throw new Error(err.error || 'Failed to start registration');
    }
    const options = await beginRes.json();

    // Step 2: browser passkey creation prompt
    let credential;
    try {
        credential = await navigator.credentials.create({
            publicKey: decodeRegistrationOptions(options),
        });
    } catch (err) {
        if (err.name === 'NotAllowedError') {
            throw new Error('Passkey creation was dismissed or timed out', { cause: err });
        }
        throw new Error(`Passkey error: ${err.message}`, { cause: err });
    }

    if (!credential) {
        throw new Error('No credential returned from authenticator');
    }

    // Step 3: send attestation to server for verification + storage
    const completeRes = await fetch(completeUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(encodeAttestation(credential)),
    });

    const result = await completeRes.json().catch(() => ({}));
    if (!completeRes.ok) {
        throw new Error(result.error || 'Passkey registration failed on server');
    }

    return result;
}
