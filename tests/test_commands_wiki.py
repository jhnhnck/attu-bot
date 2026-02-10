"""
AttuBot - Wiki Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for /wiki lookup command from wiki.py
"""

import os
import time as _time

os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, patch  # noqa: E402

import pytest  # noqa: E402

# --- /wiki lookup Command Tests ---

class TestWikiLookupCommand:
    @pytest.mark.asyncio
    async def test_lookup_single_result(self, mock_ctx):
        """Test /wiki lookup with single result (default limit)"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = AsyncMock()
        mock_wiki.search = AsyncMock(return_value=[
            {'title': 'Test Page', 'key': 'Test_Page'},
        ])
        mock_wiki.site_info = AsyncMock(return_value={
            'server': 'https://wiki.example.com',
            'articlepath': '/wiki/$1',
        })

        with patch('attubot.commands.wiki.AttuWiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Result for __test__:' in response
        assert '[Test Page]' in response
        assert 'https://wiki.example.com/wiki/Test_Page' in response

    @pytest.mark.asyncio
    async def test_lookup_multiple_results(self, mock_ctx):
        """Test /wiki lookup with multiple results"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = AsyncMock()
        mock_wiki.search = AsyncMock(return_value=[
            {'title': 'First Page', 'key': 'First_Page'},
            {'title': 'Second Page', 'key': 'Second_Page'},
            {'title': 'Third Page', 'key': 'Third_Page'},
        ])
        mock_wiki.site_info = AsyncMock(return_value={
            'server': 'https://wiki.example.com',
            'articlepath': '/wiki/$1',
        })

        with patch('attubot.commands.wiki.AttuWiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=3)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Results for __test__:' in response
        assert 'First Page' in response
        assert 'Second Page' in response
        assert 'Third Page' in response
        # Check that it's using the non-embed format with angle brackets for multiple results
        assert '(<https://wiki.example.com/wiki/First_Page>)' in response

    @pytest.mark.asyncio
    async def test_lookup_no_results(self, mock_ctx):
        """Test /wiki lookup with no results"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = AsyncMock()
        mock_wiki.search = AsyncMock(return_value=[])
        mock_wiki.site_info = AsyncMock(return_value={
            'server': 'https://wiki.example.com',
            'articlepath': '/wiki/$1',
        })

        with patch('attubot.commands.wiki.AttuWiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='nonexistent', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Oops, no results for __nonexistent__!' in response
        assert '<:rockball_player:1308977543034048552>' in response

    @pytest.mark.asyncio
    async def test_lookup_respects_limit(self, mock_ctx):
        """Test /wiki lookup respects the limit parameter"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = AsyncMock()
        mock_wiki.search = AsyncMock(return_value=[
            {'title': 'Page 1', 'key': 'Page_1'},
            {'title': 'Page 2', 'key': 'Page_2'},
        ])
        mock_wiki.site_info = AsyncMock(return_value={
            'server': 'https://wiki.example.com',
            'articlepath': '/wiki/$1',
        })

        with patch('attubot.commands.wiki.AttuWiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test', limit=2)

        # Verify search was called with correct limit
        mock_wiki.search.assert_called_once_with('test', 2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Results for __test__:' in response
        assert 'Page 1' in response
        assert 'Page 2' in response

    @pytest.mark.asyncio
    async def test_lookup_special_characters_in_title(self, mock_ctx):
        """Test /wiki lookup handles special characters in page titles"""
        from attubot.commands.wiki import wiki_lookup

        mock_wiki = AsyncMock()
        mock_wiki.search = AsyncMock(return_value=[
            {'title': 'Test: Special & Characters', 'key': 'Test:_Special_%26_Characters'},
        ])
        mock_wiki.site_info = AsyncMock(return_value={
            'server': 'https://wiki.example.com',
            'articlepath': '/wiki/$1',
        })

        with patch('attubot.commands.wiki.AttuWiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='special', limit=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Test: Special & Characters' in response
        assert 'Test:_Special_%26_Characters' in response
