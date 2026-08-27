# SPDX-License-Identifier: Apache-2.0
"""attu_server.bridge_client | signed httpx client for the bot bridge."""

import hashlib
import hmac
import time
from typing import Any

import httpx

from attu_server.config import BridgeConfig


SIGNATURE_HEADER = 'x-bridge-signature'


def _sign(secret: str, method: str, path: str, body: bytes, timestamp: int | None = None) -> str:
    """produce the bridge signature header value.

    must stay byte-for-byte equivalent to nova_core.bridge.hmac.sign;
    a unit test pins both implementations together.
    """
    ts = timestamp if timestamp is not None else int(time.time())
    payload = f'{ts}\n{method.upper()}\n{path}\n'.encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f't={ts},v1={digest}'


class BridgeError(Exception):
    """raised when the bot bridge is unreachable or returns a non-success status."""


class BridgeClient:
    """thin signed-httpx wrapper over the bot's localhost bridge.

    ttl-cached for read-only discord lookups (channels, roles, guild info, users).
    callers are responsible for invalidating when config changes.
    """

    def __init__(self, cfg: BridgeConfig, *, cache_ttl: int = 300):
        self._cfg = cfg
        self._client = httpx.AsyncClient(base_url=cfg.bot_url, timeout=cfg.request_timeout)
        self._cache_ttl = cache_ttl
        self._cache: dict[str, tuple[float, Any]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> httpx.Response:
        body = b'' if json is None else httpx.Request(method, path, json=json).content
        sig = _sign(self._cfg.secret, method, path, body)
        headers = {SIGNATURE_HEADER: sig}
        try:
            kw: dict[str, Any] = {'content': body or None, 'headers': headers}
            if params:
                kw['params'] = params
            if timeout is not None:
                kw['timeout'] = timeout
            return await self._client.request(method, path, **kw)
        except httpx.HTTPError as e:
            raise BridgeError(f'bridge request failed: {e!s}') from e

    async def _get_cached(self, key: str) -> Any | None:
        hit = self._cache.get(key)
        if hit is None:
            return None
        expiry, data = hit
        if time.time() >= expiry:
            del self._cache[key]
            return None
        return data

    def _cache_set(self, key: str, data: Any) -> None:
        self._cache[key] = (time.time() + self._cache_ttl, data)

    async def health(self) -> dict[str, Any]:
        # /bridge/health is unsigned; uses the underlying client without signing
        try:
            r = await self._client.get('/bridge/health')
        except httpx.HTTPError as e:
            raise BridgeError(f'bridge health check failed: {e!s}') from e
        r.raise_for_status()
        return r.json()

    async def get_guild_channels(self, guild_id: int) -> list[dict[str, Any]]:
        key = f'channels:{guild_id}'
        cached = await self._get_cached(key)
        if cached is not None:
            return cached
        r = await self._request('GET', f'/bridge/guilds/{guild_id}/channels')
        r.raise_for_status()
        data = r.json()['channels']
        self._cache_set(key, data)
        return data

    async def get_guild_roles(self, guild_id: int) -> list[dict[str, Any]]:
        key = f'roles:{guild_id}'
        cached = await self._get_cached(key)
        if cached is not None:
            return cached
        r = await self._request('GET', f'/bridge/guilds/{guild_id}/roles')
        r.raise_for_status()
        data = r.json()['roles']
        self._cache_set(key, data)
        return data

    async def get_guild_info(self, guild_id: int) -> dict[str, Any]:
        key = f'guild_info:{guild_id}'
        cached = await self._get_cached(key)
        if cached is not None:
            return cached
        r = await self._request('GET', f'/bridge/guilds/{guild_id}/info')
        r.raise_for_status()
        data = r.json()
        self._cache_set(key, data)
        return data

    async def get_user(self, user_id: int) -> dict[str, Any]:
        key = f'user:{user_id}'
        cached = await self._get_cached(key)
        if cached is not None:
            return cached
        r = await self._request('GET', f'/bridge/users/{user_id}')
        r.raise_for_status()
        data = r.json()
        self._cache_set(key, data)
        return data

    async def lookup_users(self, user_ids: list[int]) -> list[dict[str, Any]]:
        r = await self._request('POST', '/bridge/users/lookup', json={'user_ids': user_ids})
        r.raise_for_status()
        return r.json()['users']

    async def invalidate_guild_cache(self, guild_id: int) -> None:
        # invalidate locally first; then tell the bot
        for prefix in ('channels:', 'roles:', 'guild_info:'):
            self._cache.pop(f'{prefix}{guild_id}', None)
        r = await self._request('POST', '/bridge/cache/invalidate', json={'guild_id': guild_id})
        r.raise_for_status()

    async def trigger_reload(self, signal_type: str, guild_id: int | None = None) -> None:
        body: dict[str, Any] = {'signal_type': signal_type}
        if guild_id is not None:
            body['guild_id'] = guild_id
        r = await self._request('POST', '/bridge/reload', json=body)
        r.raise_for_status()

    async def post_op(self, path: str, json: Any = None, *, timeout: float | None = None) -> Any:
        """call a bridge ops POST endpoint; raises on non-2xx, returns parsed json."""
        r = await self._request('POST', path, json=json, timeout=timeout)
        r.raise_for_status()
        return r.json()

    async def get_op(self, path: str, params: dict | None = None, *, timeout: float | None = None) -> Any:
        """call a bridge ops GET endpoint; raises on non-2xx, returns parsed json."""
        r = await self._request('GET', path, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
