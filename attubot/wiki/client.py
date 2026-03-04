"""
AttuBot - Wiki Client
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from platform import python_version

import httpx

from attubot.logging import get_logger
from attubot.meta import __email__, __title__, __version__
from attubot.wiki.admin import AdminApi
from attubot.wiki.auth import AuthApi
from attubot.wiki.pages import PagesApi
from attubot.wiki.search import SearchApi


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
        await self.auth.login(user, key)

    async def close(self) -> None:
        """close the underlying http client"""
        await self._http.aclose()
