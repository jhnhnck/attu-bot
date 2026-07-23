"""
AttuBot - Tests for WikiClient Facade
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock

import httpx

from nova_core.wiki.admin import AdminApi
from nova_core.wiki.auth import AuthApi
from nova_core.wiki.client import WikiClient
from nova_core.wiki.pages import PagesApi
from nova_core.wiki.search import SearchApi


endpoint = 'https://wiki.example.test'


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_creates_httpx_client(self):
        """the constructor creates an httpx.AsyncClient with the provided base url."""
        wiki = WikiClient(endpoint)
        assert isinstance(wiki._http, httpx.AsyncClient)
        assert str(wiki._http.base_url).rstrip('/') == endpoint

    def test_sets_user_agent_header(self):
        """the user-agent header includes the bot title, version, and httpx version."""
        from nova_core import __email__, __title__, __version__

        wiki = WikiClient(endpoint)
        ua = wiki._http.headers['user-agent']
        assert __title__ in ua
        assert __version__ in ua
        assert __email__ in ua
        assert f'httpx/{httpx.__version__}' in ua

    def test_stores_api_paths(self):
        """the action and rest endpoint paths are stored on the instance."""
        wiki = WikiClient(endpoint)
        assert wiki._action == '/api.php'
        assert wiki._rest == '/rest.php/v1'

    def test_creates_sub_api_objects(self):
        """the constructor creates auth, pages, search, and admin sub-api instances."""
        wiki = WikiClient(endpoint)
        assert isinstance(wiki.auth, AuthApi)
        assert isinstance(wiki.pages, PagesApi)
        assert isinstance(wiki.search, SearchApi)
        assert isinstance(wiki.admin, AdminApi)

    def test_sub_apis_share_http_client(self):
        """all sub-api objects share the same httpx client instance."""
        wiki = WikiClient(endpoint)
        assert wiki.auth._client is wiki._http
        assert wiki.pages._client is wiki._http
        assert wiki.search._client is wiki._http
        assert wiki.admin._client is wiki._http


# ---------------------------------------------------------------------------
# authenticate
# ---------------------------------------------------------------------------


class TestAuthenticate:
    async def test_delegates_to_auth_login(self):
        """authenticate() calls auth.login() with the provided user and key."""
        wiki = WikiClient(endpoint)
        wiki.auth.login = AsyncMock()

        await wiki.authenticate('WikiBot@Bot', 'secret-key')

        wiki.auth.login.assert_awaited_once_with('WikiBot@Bot', 'secret-key')

    async def test_propagates_login_error(self):
        """if auth.login() raises, authenticate() propagates the exception."""
        wiki = WikiClient(endpoint)
        wiki.auth.login = AsyncMock(side_effect=httpx.HTTPStatusError('forbidden', request=None, response=None))  # type: ignore[arg-type]  # httpx tolerates None request/response in synthetic test errors

        with __import__('pytest').raises(httpx.HTTPStatusError):
            await wiki.authenticate('user', 'key')


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    async def test_closes_httpx_client(self):
        """close() calls aclose() on the underlying httpx client."""
        wiki = WikiClient(endpoint)
        wiki._http = AsyncMock(spec=httpx.AsyncClient)

        await wiki.close()

        wiki._http.aclose.assert_awaited_once()
