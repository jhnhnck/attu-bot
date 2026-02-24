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

import discord

from attubot.wiki.models import PageSummary, PageThumbnail, SearchResult, SiteInfo

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


# --- PageSummary / PageThumbnail Model Tests ---

class TestPageSummaryModel:
    def test_basic_fields(self):
        s = PageSummary(title='Test', extract='some text')
        assert s.title == 'Test'
        assert s.extract == 'some text'
        assert s.thumbnail is None

    def test_thumbnail_absent_normalizes_to_none(self):
        s = PageSummary.model_validate({'title': 'No Image', 'extract': 'text'})
        assert s.thumbnail is None

    def test_thumbnail_present(self):
        data = {
            'title': 'With Image',
            'extract': 'text',
            'thumbnail': {'source': 'https://example.com/img.png', 'width': 100, 'height': 100},
        }
        s = PageSummary.model_validate(data)
        assert s.thumbnail is not None
        assert s.thumbnail.source == 'https://example.com/img.png'

    def test_extract_defaults_to_empty_string(self):
        s = PageSummary.model_validate({'title': 'Empty'})
        assert s.extract == ''


class TestPageThumbnailModel:
    def test_fields(self):
        t = PageThumbnail(source='https://example.com/img.png', width=300, height=200)
        assert t.source == 'https://example.com/img.png'
        assert t.width == 300
        assert t.height == 200


# --- build_wiki_embed Tests ---

_SITE_INFO = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1', sitename='Test Wiki')


class TestBuildWikiEmbed:
    def test_title_and_url(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Some Page', extract='A description.')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert embed.title == 'Some Page'
        assert embed.url is None
        # link is now in the 'Open' field, not the description
        assert len(embed.fields) == 1
        assert embed.fields[0].name == 'Open'
        assert 'https://wiki.example.com/wiki/Some_Page' in embed.fields[0].value

    def test_title_with_spaces_becomes_underscores_in_url(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Page With Spaces', extract='text')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert 'Page_With_Spaces' in embed.fields[0].value

    def test_description_from_extract(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='My extract text.')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert 'My extract text.' in embed.description

    def test_empty_extract_shows_fallback(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert '_No description available._' in embed.description

    def test_long_extract_is_truncated(self):
        from attubot.commands.wiki import build_wiki_embed, _EMBED_DESC_LIMIT

        summary = PageSummary(title='T', extract='x' * (_EMBED_DESC_LIMIT + 100))
        embed = build_wiki_embed(summary, _SITE_INFO)

        # description is the extract directly; should be truncated with '...'
        assert len(embed.description) == _EMBED_DESC_LIMIT + 3  # _EMBED_DESC_LIMIT chars + '...'
        assert embed.description.endswith('...')
        # the full input length should not appear verbatim
        assert 'x' * (_EMBED_DESC_LIMIT + 100) not in embed.description

    def test_thumbnail_set_when_present(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(
            title='T',
            extract='text',
            thumbnail=PageThumbnail(source='https://example.com/img.png', width=100, height=100),
        )
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert embed.thumbnail.url == 'https://example.com/img.png'

    def test_no_thumbnail_when_absent(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='text')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert embed.thumbnail is None

    def test_footer_is_site_name(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='text')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert embed.footer.text == 'Test Wiki'

    def test_returns_discord_embed(self):
        from attubot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='text')
        embed = build_wiki_embed(summary, _SITE_INFO)

        assert isinstance(embed, discord.Embed)


# --- /wiki random Command Tests ---

class TestWikiRandomCommand:
    @pytest.mark.asyncio
    async def test_random_responds_with_embed(self, mock_ctx):
        """/wiki random sends a discord embed"""
        from attubot.commands.wiki import wiki_random

        summary = PageSummary(title='Random Page', extract='Some intro text.')
        site_info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1', sitename='Test Wiki')

        mock_wiki = MagicMock()
        mock_wiki.pages.get_random_summary = AsyncMock(return_value=summary)
        mock_wiki.search.site_info = AsyncMock(return_value=site_info)

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_random(mock_ctx)

        mock_ctx.respond.assert_called_once()
        call_kwargs = mock_ctx._responses[0]['kwargs']
        embed = call_kwargs['embed']
        assert isinstance(embed, discord.Embed)
        assert embed.title == 'Random Page'
        assert 'Some intro text.' in embed.description

    @pytest.mark.asyncio
    async def test_random_defers_before_fetch(self, mock_ctx):
        """/wiki random defers the response before hitting the api"""
        from attubot.commands.wiki import wiki_random

        summary = PageSummary(title='P', extract='text')
        site_info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1')

        mock_wiki = MagicMock()
        mock_wiki.pages.get_random_summary = AsyncMock(return_value=summary)
        mock_wiki.search.site_info = AsyncMock(return_value=site_info)

        defer_order = []
        original_defer = mock_ctx.defer
        original_respond = mock_ctx.respond

        async def tracking_defer():
            defer_order.append('defer')
            await original_defer()

        async def tracking_respond(**kwargs):
            defer_order.append('respond')
            await original_respond(**kwargs)

        mock_ctx.defer = tracking_defer
        mock_ctx.respond = tracking_respond

        with patch('attubot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_random(mock_ctx)

        assert defer_order == ['defer', 'respond']
