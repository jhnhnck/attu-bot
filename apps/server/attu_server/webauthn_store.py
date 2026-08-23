# SPDX-License-Identifier: Apache-2.0
"""attu_server.webauthn_store | TTL-backed challenge storage for webauthn ceremonies."""

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from attu_models.connection import MongoStorage


COLLECTION = 'webauthn_challenges'
TTL_SECONDS = 300


async def ensure_indexes(storage: MongoStorage) -> None:
    """create the TTL index on `expires_at`. server is the leader for this collection."""
    db = storage.get_db()
    await db[COLLECTION].create_index('nonce', unique=True)
    await db[COLLECTION].create_index('expires_at', expireAfterSeconds=0)


async def put(storage: MongoStorage, payload: dict[str, Any]) -> str:
    """store the challenge payload under a freshly minted nonce; returns the nonce."""
    nonce = secrets.token_urlsafe(32)
    expires_at = datetime.now(tz=UTC) + timedelta(seconds=TTL_SECONDS)
    await storage.get_db()[COLLECTION].insert_one({
        'nonce': nonce,
        'payload': payload,
        'expires_at': expires_at,
    })
    return nonce


async def pop(storage: MongoStorage, nonce: str) -> dict[str, Any] | None:
    """atomically read + delete the challenge for `nonce`; returns None if expired or absent."""
    doc = await storage.get_db()[COLLECTION].find_one_and_delete({'nonce': nonce})
    if doc is None:
        return None
    # a doc that just expired but mongo has not yet purged is still atomically removed by find_one_and_delete;
    # in that case its expires_at is in the past - treat as absent so callers don't replay
    expires_at = doc.get('expires_at')
    if expires_at is not None and expires_at < datetime.now(tz=UTC):
        return None
    return doc.get('payload')
