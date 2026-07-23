# SPDX-License-Identifier: Apache-2.0
"""nova_core.bridge.hmac | request signing + verification for the bridge."""

from __future__ import annotations

import contextlib
import hashlib
import hmac as _hmac
import time

from nova_core.client.core import config


SIGNATURE_HEADER = 'x-bridge-signature'

# fastapi is absent in unit/component test containers; kept in globals so FastAPI's
# get_type_hints() can resolve the 'Request' annotation in verify() at route-registration time.
with contextlib.suppress(ImportError):
    from fastapi import HTTPException, Request  # noqa: F401 - module-global for get_type_hints(); sign() does not need these


def sign(secret: str, method: str, path: str, body: bytes, timestamp: int | None = None) -> str:
    """produce an x-bridge-signature header value for a request.

    callers (the server's bridge_client, e2e tests) build the same payload from the
    outbound request and attach the result as the signature header.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    payload = f'{ts}\n{method.upper()}\n{path}\n'.encode() + body
    digest = _hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f't={ts},v1={digest}'


def _parse_header(value: str) -> tuple[int, str]:
    parts: dict[str, str] = {}
    for part in value.split(','):
        k, _, v = part.partition('=')
        parts[k.strip()] = v.strip()
    return int(parts['t']), parts['v1']


async def verify(request: Request) -> None:
    """fastapi dependency; rejects requests with missing, stale, or invalid signatures."""
    from fastapi import HTTPException  # lazy: not needed by sign(); absent in unit/component test containers

    header = request.headers.get(SIGNATURE_HEADER)
    if not header:
        raise HTTPException(status_code=401, detail='missing bridge signature')

    try:
        ts, sig = _parse_header(header)
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=401, detail='malformed bridge signature') from e

    now = int(time.time())
    if abs(now - ts) > config.bridge.replay_window:
        raise HTTPException(status_code=401, detail='stale bridge signature')

    body = await request.body()
    expected = sign(config.bridge.secret, request.method, request.url.path, body, ts)
    _, expected_sig = _parse_header(expected)

    if not _hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=401, detail='invalid bridge signature')
