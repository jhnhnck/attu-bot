# SPDX-License-Identifier: Apache-2.0
"""attu_wiki.client | wiki client."""

import httpx
import structlog

from attu_wiki.admin import AdminApi
from attu_wiki.auth import AuthApi
from attu_wiki.pages import PagesApi
from attu_wiki.search import SearchApi


logger = structlog.stdlib.get_logger(__name__)


class WikiClient:
    """
    facade over the mediawiki action and REST apis.

    usage:
        wiki = WikiClient(endpoint='https://wiki.example.com', user_agent='MyBot/1.0')
        await wiki.authenticate(user, key)  # only needed for write ops
        results = await wiki.search.search('query', limit=5)
        text = await wiki.pages.get('Page Title')
    """

    def __init__(self, endpoint: str, user_agent: str):
        self._http = httpx.AsyncClient(
            base_url=endpoint,
            headers={
                'User-Agent': user_agent,
            },
        )

        self._action = '/api.php'
        self._rest = '/rest.php/v1'

        self.auth = AuthApi(self._http, self._action)
        self.pages = PagesApi(self._http, self._action, self.auth)
        self.search = SearchApi(self._http, self._action, self._rest)
        self.admin = AdminApi(self._http, self._action, self.auth)

    async def authenticate(self, user: str, key: str) -> None:
        """log in to the wiki; required before any write/admin operations."""
        logger.debug('authenticating to wiki', user=user)
        await self.auth.login(user, key)
        logger.info('wiki authenticated', user=user)

    async def close(self) -> None:
        """close the underlying http client."""
        logger.debug('closing wiki http client')
        await self._http.aclose()
