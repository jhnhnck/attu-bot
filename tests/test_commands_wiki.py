"""
AttuBot - Wiki Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for /wiki lookup command from commands/wiki.py
"""

import os
import time as _time

os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.wiki.models import SearchResult, SiteInfo

def _make_mock_wiki(pages: list[dict], site: dict | None = None):
    """build a mock WikiClient whose search api returns the given pages"""
    if site is None:
        site = {'server': 'https://wiki.example.com', 'articlepath': '/wiki/$1'}

    site_info = SiteInfo.model_validate(site)
    results = [SearchResult.model_validate(p) for p in pages]

    mock = MagicMock()
    mock.search = MagicMock()
    mock.search.search = AsyncMock(return_value=results)
    mock.search.site_info = AsyncMock(return_value=site_info)
    return mock


# --- /wiki lookup Command Tests ---

class TestWikiLookupCommand:
    @pytest.mark.asyncio
    async def test_lookup_single_result(self, mock_ctx):
        """/wiki lookup with single result"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([{'title': 'Test Page', 'key': 'Test_Page'}])

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Result for __test__:' in response
        assert '[Test Page]' in response
        assert 'https://wiki.example.com/wiki/Test_Page' in response

    @pytest.mark.asyncio
    async def test_lookup_multiple_results(self, mock_ctx):
        """/wiki lookup with multiple results"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([
            {'title': 'First Page', 'key': 'First_Page'},
            {'title': 'Second Page', 'key': 'Second_Page'},
            {'title': 'Third Page', 'key': 'Third_Page'},
        ])

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=3)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Results for __test__:' in response
        assert 'First Page' in response
        assert 'Second Page' in response
        assert 'Third Page' in response
        # multi-result links use angle-bracket format to suppress embeds
        assert '(<https://wiki.example.com/wiki/First_Page>)' in response

    @pytest.mark.asyncio
    async def test_lookup_no_results(self, mock_ctx):
        """/wiki lookup with no results"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([])

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='nonexistent', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Oops, no results for __nonexistent__!' in response
        assert '<:rockball_player:1308977543034048552>' in response

    @pytest.mark.asyncio
    async def test_lookup_respects_limit(self, mock_ctx):
        """/wiki lookup passes limit through to the search api"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([
            {'title': 'Page 1', 'key': 'Page_1'},
            {'title': 'Page 2', 'key': 'Page_2'},
        ])

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=2)

        mock_wiki.search.search.assert_called_once_with('test', 2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Results for __test__:' in response
        assert 'Page 1' in response
        assert 'Page 2' in response

    @pytest.mark.asyncio
    async def test_lookup_special_characters_in_title(self, mock_ctx):
        """/wiki lookup handles special characters in page titles"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([
            {'title': 'Test: Special & Characters', 'key': 'Test:_Special_%26_Characters'},
        ])

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='special', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Test: Special & Characters' in response
        assert 'Test:_Special_%26_Characters' in response


# --- SiteInfo Model Tests ---

class TestSiteInfoModel:
    def test_page_url_replaces_placeholder(self):
        info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1')
        assert info.page_url('Some_Page') == 'https://wiki.example.com/wiki/Some_Page'

    def test_page_url_with_encoded_key(self):
        info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1')
        assert info.page_url('Test:_Special_%26_Characters') == 'https://wiki.example.com/wiki/Test:_Special_%26_Characters'

    def test_model_accepts_alias_fields(self):
        info = SiteInfo.model_validate({'server': 'https://example.com', 'articlepath': '/w/$1', 'sitename': 'My Wiki', 'generator': 'MediaWiki 1.40'})
        assert info.site_name == 'My Wiki'
        assert info.generator == 'MediaWiki 1.40'


# --- SearchResult Model Tests ---

class TestSearchResultModel:
    def test_required_fields(self):
        r = SearchResult(title='Hello', key='Hello')
        assert r.title == 'Hello'
        assert r.key == 'Hello'
        assert r.excerpt == ''

    def test_optional_fields_default(self):
        r = SearchResult(title='T', key='T')
        assert r.matched_title is None
        assert r.description is None

    def test_model_validate_from_dict(self):
        r = SearchResult.model_validate({'title': 'A Page', 'key': 'A_Page', 'excerpt': 'some text'})
        assert r.title == 'A Page'
        assert r.excerpt == 'some text'
