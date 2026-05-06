"""
AttuBot - Wiki HTTP Boundary Tests (respx)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests the three wiki API layers (auth, search, admin) against a mocked HTTP
transport.  No real network calls are made.
"""

from unittest.mock import patch

import httpx
import pytest
import respx

from doom_bot.wiki.admin import AdminApi
from doom_bot.wiki.auth import AuthApi
from doom_bot.wiki.models import SearchResult, SiteInfo
from doom_bot.wiki.search import SearchApi


pytestmark = pytest.mark.unit

action = 'https://wiki.example.test/api.php'
rest = 'https://wiki.example.test/rest.php/v1'
base = 'https://wiki.example.test'


# ============================================================
# shared fixtures
# ============================================================


@pytest.fixture
def http_client():
    """real httpx async client pointed at the test base url"""
    client = httpx.AsyncClient(base_url=base)
    return client


@pytest.fixture
def auth(http_client):
    return AuthApi(http_client, '/api.php')


@pytest.fixture
def search(http_client):
    return SearchApi(http_client, '/api.php', '/rest.php/v1')


@pytest.fixture
def admin(http_client, auth):
    return AdminApi(http_client, '/api.php', auth)


# ============================================================
# AuthApi
# ============================================================


class TestAuthApiGetCsrf:
    @respx.mock
    async def test_success_returns_token(self, auth):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'abc+\\'}}}))
        token = await auth.get_csrf()
        assert token == 'abc+\\'  # noqa: S105

    @respx.mock
    async def test_non_2xx_raises(self, auth):
        respx.get(action).mock(return_value=httpx.Response(403, text='forbidden'))
        with pytest.raises(httpx.HTTPStatusError):
            await auth.get_csrf()

    @respx.mock
    async def test_missing_key_raises(self, auth):
        """documents current behavior: malformed payload raises KeyError"""
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {}}))
        with pytest.raises(KeyError):
            await auth.get_csrf()

    @respx.mock
    async def test_request_params(self, auth):
        """assert correct query params are sent"""
        route = respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        await auth.get_csrf()
        assert route.called
        params = dict(route.calls[0].request.url.params)
        assert params['action'] == 'query'
        assert params['meta'] == 'tokens'
        assert params['format'] == 'json'


class TestAuthApiLogin:
    @respx.mock
    async def test_success_path(self, auth):
        """two-step: GET login token then POST credentials"""
        get_route = respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'logintoken': 'lt123'}}}))
        post_route = respx.post(action).mock(return_value=httpx.Response(200, json={'login': {'result': 'Success'}}))
        await auth.login('WikiBot@Bot', 'secret-key')
        assert get_route.called
        assert post_route.called

    @respx.mock
    async def test_login_token_fetch_failure_raises(self, auth):
        respx.get(action).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await auth.login('user', 'key')

    @respx.mock
    async def test_login_post_failure_raises(self, auth):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'logintoken': 'tok'}}}))
        respx.post(action).mock(return_value=httpx.Response(403, text='denied'))
        with pytest.raises(httpx.HTTPStatusError):
            await auth.login('user', 'key')

    @respx.mock
    async def test_post_body_contains_credentials(self, auth):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'logintoken': 'mytoken'}}}))
        post_route = respx.post(action).mock(return_value=httpx.Response(200, json={}))
        await auth.login('MyUser@Bot', 'my-secret')
        content = post_route.calls[0].request.content.decode()
        assert 'lgname=MyUser%40Bot' in content or 'lgname=MyUser' in content
        assert 'mytoken' in content


# ============================================================
# SearchApi
# ============================================================


class TestSearchApiSearch:
    @respx.mock
    async def test_returns_results(self, search):
        respx.get(f'{rest}/search/page').mock(
            return_value=httpx.Response(
                200,
                json={
                    'pages': [
                        {'title': 'Alpha', 'key': 'Alpha'},
                        {'title': 'Beta', 'key': 'Beta'},
                    ]
                },
            )
        )
        results = await search.search('test', limit=5)
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].title == 'Alpha'

    @respx.mock
    async def test_truncates_to_limit(self, search):
        """api returned more results than requested; client truncates"""
        respx.get(f'{rest}/search/page').mock(return_value=httpx.Response(200, json={'pages': [{'title': str(i), 'key': str(i)} for i in range(10)]}))
        results = await search.search('q', limit=3)
        assert len(results) == 3

    @respx.mock
    async def test_missing_pages_key_returns_empty(self, search):
        respx.get(f'{rest}/search/page').mock(return_value=httpx.Response(200, json={}))
        results = await search.search('q', limit=5)
        assert results == []

    @respx.mock
    async def test_non_2xx_raises(self, search):
        respx.get(f'{rest}/search/page').mock(return_value=httpx.Response(404))
        with pytest.raises(httpx.HTTPStatusError):
            await search.search('q', limit=5)

    @respx.mock
    async def test_optional_fields_absent(self, search):
        """pages with only required fields should parse correctly"""
        respx.get(f'{rest}/search/page').mock(
            return_value=httpx.Response(
                200,
                json={
                    'pages': [
                        {'title': 'Min Page', 'key': 'Min_Page'},
                    ]
                },
            )
        )
        results = await search.search('q', limit=5)
        assert results[0].excerpt is None
        assert results[0].matched_title is None
        assert results[0].description is None

    @respx.mock
    async def test_all_optional_fields_present(self, search):
        respx.get(f'{rest}/search/page').mock(
            return_value=httpx.Response(
                200,
                json={
                    'pages': [
                        {
                            'title': 'Full Page',
                            'key': 'Full_Page',
                            'excerpt': 'An excerpt.',
                            'matched_title': 'Full',
                            'description': 'A short desc.',
                        },
                    ]
                },
            )
        )
        results = await search.search('q', limit=5)
        r = results[0]
        assert r.excerpt == 'An excerpt.'
        assert r.matched_title == 'Full'
        assert r.description == 'A short desc.'

    @respx.mock
    async def test_request_params(self, search):
        route = respx.get(f'{rest}/search/page').mock(return_value=httpx.Response(200, json={'pages': []}))
        await search.search('my query', limit=7)
        params = dict(route.calls[0].request.url.params)
        assert params['q'] == 'my query'
        assert params['limit'] == '7'


class TestSearchApiSearchTitle:
    @respx.mock
    async def test_returns_results(self, search):
        respx.get(f'{rest}/search/title').mock(
            return_value=httpx.Response(
                200,
                json={
                    'pages': [
                        {'title': 'Exact Match', 'key': 'Exact_Match'},
                    ]
                },
            )
        )
        results = await search.search_title('exact', limit=1)
        assert len(results) == 1
        assert results[0].title == 'Exact Match'

    @respx.mock
    async def test_truncates_to_limit(self, search):
        respx.get(f'{rest}/search/title').mock(return_value=httpx.Response(200, json={'pages': [{'title': str(i), 'key': str(i)} for i in range(5)]}))
        results = await search.search_title('q', limit=2)
        assert len(results) == 2

    @respx.mock
    async def test_missing_pages_key_returns_empty(self, search):
        respx.get(f'{rest}/search/title').mock(return_value=httpx.Response(200, json={}))
        results = await search.search_title('q', limit=1)
        assert results == []

    @respx.mock
    async def test_non_2xx_raises(self, search):
        respx.get(f'{rest}/search/title').mock(return_value=httpx.Response(503))
        with pytest.raises(httpx.HTTPStatusError):
            await search.search_title('q', limit=1)


class TestSearchApiSiteInfo:
    @respx.mock
    async def test_success_parses_aliases(self, search):
        respx.post(action).mock(
            return_value=httpx.Response(
                200,
                json={
                    'query': {
                        'general': {
                            'server': 'https://wiki.example.test',
                            'articlepath': '/wiki/$1',
                            'sitename': 'Test Wiki',
                            'generator': 'MediaWiki 1.40',
                        }
                    }
                },
            )
        )
        info = await search.site_info()
        assert isinstance(info, SiteInfo)
        assert info.server == 'https://wiki.example.test'
        assert info.article_path == '/wiki/$1'
        assert info.site_name == 'Test Wiki'
        assert info.generator == 'MediaWiki 1.40'

    @respx.mock
    async def test_optional_fields_default(self, search):
        respx.post(action).mock(
            return_value=httpx.Response(
                200,
                json={
                    'query': {
                        'general': {
                            'server': 'https://wiki.example.test',
                            'articlepath': '/wiki/$1',
                        }
                    }
                },
            )
        )
        info = await search.site_info()
        assert info.site_name == ''
        assert info.generator == ''

    @respx.mock
    async def test_page_url_uses_article_path(self, search):
        respx.post(action).mock(return_value=httpx.Response(200, json={'query': {'general': {'server': 'https://wiki.example.test', 'articlepath': '/w/$1'}}}))
        info = await search.site_info()
        assert info.page_url('Foo_Bar') == 'https://wiki.example.test/w/Foo_Bar'

    @respx.mock
    async def test_non_2xx_raises(self, search):
        respx.post(action).mock(return_value=httpx.Response(500))
        with pytest.raises(httpx.HTTPStatusError):
            await search.site_info()

    @respx.mock
    async def test_malformed_payload_raises(self, search):
        respx.post(action).mock(return_value=httpx.Response(200, json={'not_query': {}}))
        with pytest.raises(KeyError):
            await search.site_info()


# ============================================================
# AdminApi
# ============================================================


class TestAdminApiBlock:
    @respx.mock
    async def test_success_returns_true(self, admin):
        # csrf fetch
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        # block post
        respx.post(action).mock(return_value=httpx.Response(200, json={'block': {'user': 'BadUser'}}))

        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await admin.block('BadUser', reason='spam')

        assert result is True
        mock_sleep.assert_not_called()

    @respx.mock
    async def test_retry_then_success_returns_true(self, admin):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        # fail twice, succeed on third
        respx.post(action).mock(
            side_effect=[
                httpx.Response(503),
                httpx.Response(503),
                httpx.Response(200, json={'block': {}}),
            ]
        )

        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await admin.block('SpamUser', reason='spam', max_retries=3)

        assert result is True
        assert mock_sleep.call_count == 2

    @respx.mock
    async def test_exhaust_retries_returns_false(self, admin):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        respx.post(action).mock(return_value=httpx.Response(500))

        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await admin.block('User', reason='spam', max_retries=3)

        assert result is False
        assert mock_sleep.call_count == 3

    @respx.mock
    async def test_backoff_uses_3_second_sleep(self, admin):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        respx.post(action).mock(return_value=httpx.Response(500))

        sleep_calls = []

        async def capture_sleep(seconds):
            sleep_calls.append(seconds)

        with patch('asyncio.sleep', side_effect=capture_sleep):
            await admin.block('User', reason='test', max_retries=2)

        assert all(s == 3 for s in sleep_calls)

    @respx.mock
    async def test_csrf_fetch_on_each_block_call(self, admin):
        """get_csrf is called once per block() call"""
        csrf_route = respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        respx.post(action).mock(return_value=httpx.Response(200, json={'block': {}}))

        with patch('asyncio.sleep', new=AsyncMock()):
            await admin.block('User', reason='test')

        assert csrf_route.call_count == 1

    @respx.mock
    async def test_block_post_body(self, admin):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'mycsrf'}}}))
        post_route = respx.post(action).mock(return_value=httpx.Response(200, json={'block': {}}))

        with patch('asyncio.sleep', new=AsyncMock()):
            await admin.block('TargetUser', reason='vandalism')

        body = post_route.calls[0].request.content.decode()
        assert 'user=TargetUser' in body
        assert 'reason=vandalism' in body
        assert 'mycsrf' in body
        assert 'action=block' in body

    @respx.mock
    async def test_default_max_retries_is_3(self, admin):
        respx.get(action).mock(return_value=httpx.Response(200, json={'query': {'tokens': {'csrftoken': 'tok'}}}))
        respx.post(action).mock(return_value=httpx.Response(500))

        with patch('asyncio.sleep', new=AsyncMock()) as mock_sleep:
            result = await admin.block('User', reason='test')  # uses default max_retries=3

        assert result is False
        assert mock_sleep.call_count == 3


from unittest.mock import AsyncMock
