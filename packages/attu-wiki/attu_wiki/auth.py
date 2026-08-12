# SPDX-License-Identifier: Apache-2.0
"""attu_wiki.auth | wiki authentication."""

import httpx
import structlog


logger = structlog.stdlib.get_logger(__name__)


class AuthApi:
    """handles mediawiki authentication and csrf token fetching"""

    def __init__(self, client: httpx.AsyncClient, action_endpoint: str):
        self._client = client
        self._endpoint = action_endpoint

    async def get_csrf(self) -> str:
        """fetch a csrf token for write operations"""
        res = await self._client.get(
            self._endpoint,
            params={'action': 'query', 'meta': 'tokens', 'format': 'json'},
        )
        res.raise_for_status()
        return res.json()['query']['tokens']['csrftoken']

    async def login(self, user: str, key: str) -> None:
        """log in with a bot username and password"""
        res = await self._client.get(
            self._endpoint,
            params={'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'},
        )
        res.raise_for_status()
        login_token = res.json()['query']['tokens']['logintoken']

        data = {
            'action': 'login',
            'lgname': user,
            'lgpassword': key,
            'lgtoken': login_token,
            'format': 'json',
        }

        res = await self._client.post(self._endpoint, data=data)
        res.raise_for_status()
        logger.debug(res.text)
