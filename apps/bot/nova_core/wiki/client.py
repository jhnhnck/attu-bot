# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki.client | wiki client."""

from platform import python_version

import httpx

from nova_core import __email__, __title__, __version__
from nova_core.logging import get_logger
from nova_core.wiki.admin import AdminApi
from nova_core.wiki.auth import AuthApi
from nova_core.wiki.pages import PagesApi
from nova_core.wiki.search import SearchApi


logger = get_logger(__name__)


class WikiClient:
    """
    facade over the mediawiki action and REST apis.

    usage:
        wiki = WikiClient(endpoint='https://wiki.example.com')
        await wiki.authenticate(user, key)  # only needed for write ops
        results = await wiki.search.search('query', limit=5)
        text = await wiki.pages.get('Page Title')
    """

    def __init__(self, endpoint: str):
        self._http = httpx.AsyncClient(
            base_url=endpoint,
            headers={
                'User-Agent': f'{__title__}/{__version__} ({__email__}) httpx/{httpx.__version__} Python/{python_version()}',
            },
        )

        self._action = '/api.php'
        self._rest = '/rest.php/v1'

        # build the api surface from shared client + endpoints
        self.auth = AuthApi(self._http, self._action)
        self.pages = PagesApi(self._http, self._action, self.auth)
        self.search = SearchApi(self._http, self._action, self._rest)
        self.admin = AdminApi(self._http, self._action, self.auth)

    async def authenticate(self, user: str, key: str) -> None:
        """log in to the wiki; required before any write/admin operations"""
        logger.debug('authenticating to wiki', user=user)
        await self.auth.login(user, key)
        logger.info('wiki authenticated', user=user)

    async def close(self) -> None:
        """close the underlying http client"""
        logger.debug('closing wiki http client')
        await self._http.aclose()
