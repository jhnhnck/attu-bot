# SPDX-License-Identifier: Apache-2.0
"""attu_wiki.admin | wiki admin operations."""

import asyncio

import httpx
import structlog

from attu_wiki.auth import AuthApi


logger = structlog.stdlib.get_logger(__name__)


class AdminApi:
    """handles privileged wiki operations that require authentication."""

    def __init__(self, client: httpx.AsyncClient, action_endpoint: str, auth: AuthApi):
        self._client = client
        self._endpoint = action_endpoint
        self._auth = auth

    async def block(self, user: str, reason: str, max_retries: int = 3) -> bool:
        """block a user from the wiki; retries up to max_retries times on failure."""
        csrf = await self._auth.get_csrf()

        data = {
            'action': 'block',
            'format': 'json',
            'user': user,
            'expiry': 'never',
            'reason': reason,
            'nocreate': True,
            'autoblock': True,
            'noemail': True,
            'reblock': True,
            'token': csrf,
        }

        for attempt in range(max_retries):
            try:
                res = await self._client.post(self._endpoint, data=data)
                res.raise_for_status()
                logger.debug(res.text)
                return True

            except Exception:
                logger.exception(f'block(): attempt {attempt + 1} failed')
                await asyncio.sleep(3)

        return False
