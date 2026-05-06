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

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from doom_bot.wiki.models import PageSummary, PageThumbnail, SearchResult, SiteInfo


def _make_mock_view_repo():
    """build a mock WikiViewRepository"""
    repo = MagicMock()
    repo.upsert = AsyncMock()
    repo.get = AsyncMock(return_value=None)
    repo.delete = AsyncMock()
    return repo


@contextmanager
def _patch_wiki_multi(mock_wiki, mock_view_repo=None):
    """patch context for multi-result wiki tests"""
    if mock_view_repo is None:
        mock_view_repo = _make_mock_view_repo()
    mock_bot = MagicMock()
    mock_bot.add_view = MagicMock()
    with (
        patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki),
        patch('doom_bot.commands.wiki._wiki_view_repo', mock_view_repo),
        patch('doom_bot.commands.wiki.bot', mock_bot),
    ):
        yield mock_bot


def _make_mock_wiki(pages: list[dict], site: dict | None = None, summary: PageSummary | None = None, title_pages: list[dict] | None = None):
    """build a mock WikiClient whose search api returns the given pages"""
    if site is None:
        site = {'server': 'https://wiki.example.com', 'articlepath': '/wiki/$1'}

    site_info = SiteInfo.model_validate(site)
    results = [SearchResult.model_validate(p) for p in pages]
    title_results = [SearchResult.model_validate(p) for p in (title_pages or [])]

    mock = MagicMock()
    mock.search = MagicMock()
    mock.search.search = AsyncMock(return_value=results)
    mock.search.search_title = AsyncMock(return_value=title_results)
    mock.search.site_info = AsyncMock(return_value=site_info)
    mock.pages = MagicMock()
    mock.pages.get_summary = AsyncMock(return_value=summary)
    return mock


# --- /wiki lookup Command Tests ---


class TestWikiLookupCommand:
    @pytest.mark.asyncio
    async def test_lookup_single_result(self, mock_ctx):
        """/wiki lookup with single result responds with embed"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Test Page', extract='A description.')
        mock_wiki = _make_mock_wiki([{'title': 'Test Page', 'key': 'Test_Page'}], summary=summary)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        mock_ctx.respond.assert_called_once()
        call_kwargs = mock_ctx._responses[0]['kwargs']
        embed = call_kwargs['embed']
        assert isinstance(embed, discord.Embed)
        assert embed.title == 'Test Page'

    @pytest.mark.asyncio
    async def test_lookup_single_result_has_link_button(self, mock_ctx):
        """/wiki lookup with single result includes the open wiki link button"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Test Page', extract='A description.')
        mock_wiki = _make_mock_wiki([{'title': 'Test Page', 'key': 'Test_Page'}], summary=summary)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        call_kwargs = mock_ctx._responses[0]['kwargs']
        view = call_kwargs['view']
        assert view is not None
        link_buttons = [c for c in view.children if isinstance(c, discord.ui.Button) and c.style == discord.ButtonStyle.link]
        assert len(link_buttons) == 1
        assert link_buttons[0].label == 'Open Wiki!'
        assert link_buttons[0].url is not None
        assert 'wiki.example.com' in link_buttons[0].url

    @pytest.mark.asyncio
    async def test_lookup_multiple_results_has_nav_buttons(self, mock_ctx):
        """/wiki lookup with multiple results includes prev/next nav buttons"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='First Page', extract='text')
        mock_wiki = _make_mock_wiki(
            [
                {'title': 'First Page', 'key': 'First_Page'},
                {'title': 'Second Page', 'key': 'Second_Page'},
            ],
            summary=summary,
        )

        with _patch_wiki_multi(mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        # multi-result: view is attached via message.edit, not the initial respond
        message = await mock_ctx.interaction.original_response()
        message.edit.assert_called_once()
        view = message.edit.call_args.kwargs['view']
        assert view is not None
        non_link_buttons = [c for c in view.children if isinstance(c, discord.ui.Button) and c.style != discord.ButtonStyle.link]
        labels = [b.label for b in non_link_buttons if b.label is not None]
        assert 'Previous' in labels
        assert any('Next' in label for label in labels)

    @pytest.mark.asyncio
    async def test_lookup_no_results(self, mock_ctx):
        """/wiki lookup with no results sends an error message"""
        from doom_bot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki([])

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='nonexistent')

        mock_ctx.respond.assert_called_once()
        # the error case still sends text, not an embed
        response = mock_ctx._responses[0]['args']
        assert len(response) > 0
        assert 'Oops, no results for __nonexistent__!' in response[0]
        assert '<:rockball_player:1308977543034048552>' in response[0]

    @pytest.mark.asyncio
    async def test_lookup_always_searches_with_max_limit(self, mock_ctx):
        """/wiki lookup always calls the search api with the hardcoded limit of 11"""
        from doom_bot.commands.wiki import _SEARCH_LIMIT, wiki_lookup

        summary = PageSummary(title='Page 1', extract='text')
        mock_wiki = _make_mock_wiki([{'title': 'Page 1', 'key': 'Page_1'}], summary=summary)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        mock_wiki.search.search.assert_called_once_with('test', _SEARCH_LIMIT)

    @pytest.mark.asyncio
    async def test_lookup_fetches_summary_for_first_result(self, mock_ctx):
        """/wiki lookup fetches the page summary for the first result"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Test Page', extract='some text')
        mock_wiki = _make_mock_wiki(
            [
                {'title': 'Test Page', 'key': 'Test_Page'},
                {'title': 'Other Page', 'key': 'Other_Page'},
            ],
            summary=summary,
        )

        with _patch_wiki_multi(mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        mock_wiki.pages.get_summary.assert_called_once_with('Test Page')

    @pytest.mark.asyncio
    async def test_lookup_falls_back_when_summary_is_none(self, mock_ctx):
        """/wiki lookup uses search excerpt as fallback when get_summary returns None"""
        from doom_bot.commands.wiki import wiki_lookup

        mock_wiki = _make_mock_wiki(
            [{'title': 'Missing Page', 'key': 'Missing_Page', 'excerpt': 'short excerpt'}],
            summary=None,
        )

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='missing')

        call_kwargs = mock_ctx._responses[0]['kwargs']
        embed = call_kwargs['embed']
        assert embed.title == 'Missing Page'
        assert embed.description is not None
        assert 'short excerpt' in embed.description

    @pytest.mark.asyncio
    async def test_lookup_calls_search_title_with_limit_1(self, mock_ctx):
        """/wiki lookup calls search_title with limit 1"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Page 1', extract='text')
        mock_wiki = _make_mock_wiki([{'title': 'Page 1', 'key': 'Page_1'}], summary=summary)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        mock_wiki.search.search_title.assert_called_once_with('test', 1)

    @pytest.mark.asyncio
    async def test_lookup_title_result_is_first(self, mock_ctx):
        """title search result appears before body results"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Title Match', extract='exact match')
        mock_wiki = _make_mock_wiki(
            pages=[{'title': 'Body Result', 'key': 'Body_Result'}],
            title_pages=[{'title': 'Title Match', 'key': 'Title_Match'}],
            summary=summary,
        )

        with _patch_wiki_multi(mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        mock_wiki.pages.get_summary.assert_called_once_with('Title Match')

    @pytest.mark.asyncio
    async def test_lookup_deduplicates_title_and_body_overlap(self, mock_ctx):
        """pages returned by both searches are not duplicated"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='Shared Page', extract='text')
        mock_wiki = _make_mock_wiki(
            pages=[
                {'title': 'Shared Page', 'key': 'Shared_Page'},
                {'title': 'Other Page', 'key': 'Other_Page'},
            ],
            title_pages=[{'title': 'Shared Page', 'key': 'Shared_Page'}],
            summary=summary,
        )

        with _patch_wiki_multi(mock_wiki):
            await wiki_lookup(mock_ctx, query='test')

        # only 2 unique pages - no duplicate of 'Shared Page'
        # multi-result: view is attached via message.edit
        message = await mock_ctx.interaction.original_response()
        view = message.edit.call_args.kwargs['view']
        assert len(view._pages) == 2

    @pytest.mark.asyncio
    async def test_lookup_defers_before_fetch(self, mock_ctx):
        """/wiki lookup defers before hitting the api"""
        from doom_bot.commands.wiki import wiki_lookup

        summary = PageSummary(title='T', extract='text')
        mock_wiki = _make_mock_wiki([{'title': 'T', 'key': 'T'}], summary=summary)

        defer_order = []
        original_defer = mock_ctx.defer
        original_respond = mock_ctx.respond

        async def tracking_defer():
            defer_order.append('defer')
            await original_defer()

        async def tracking_respond(*args, **kwargs):
            defer_order.append('respond')
            await original_respond(*args, **kwargs)

        mock_ctx.defer = tracking_defer
        mock_ctx.respond = tracking_respond

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_lookup(mock_ctx, query='t')

        assert defer_order[0] == 'defer'
        assert 'respond' in defer_order


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
        assert r.excerpt is None

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
    def test_returns_embed_and_url(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Some Page', extract='A description.')
        result = build_wiki_embed(summary, _SITE_INFO)

        assert isinstance(result, tuple)
        assert len(result) == 2
        embed, url = result
        assert isinstance(embed, discord.Embed)
        assert isinstance(url, str)

    def test_url_contains_page_key(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Some Page', extract='A description.')
        _, url = build_wiki_embed(summary, _SITE_INFO)

        assert url == 'https://wiki.example.com/wiki/Some_Page'

    def test_no_open_field_in_embed(self):
        """the open url is now returned as a separate value, not an embed field"""
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Some Page', extract='A description.')
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert len(embed.fields) == 0

    def test_title_with_spaces_becomes_underscores_in_url(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='Page With Spaces', extract='text')
        _, url = build_wiki_embed(summary, _SITE_INFO)

        assert 'Page_With_Spaces' in url

    def test_description_from_extract(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='My extract text.')
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.description is not None
        assert 'My extract text.' in embed.description

    def test_empty_extract_shows_fallback(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='')
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.description is not None
        assert '_No description available._' in embed.description

    def test_long_extract_is_truncated(self):
        from doom_bot.commands.wiki import _EMBED_DESC_LIMIT, build_wiki_embed

        summary = PageSummary(title='T', extract='x' * (_EMBED_DESC_LIMIT + 100))
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.description is not None
        assert len(embed.description) == _EMBED_DESC_LIMIT + 3  # _EMBED_DESC_LIMIT chars + '...'
        assert embed.description.endswith('...')
        assert 'x' * (_EMBED_DESC_LIMIT + 100) not in embed.description

    def test_thumbnail_set_when_present(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(
            title='T',
            extract='text',
            thumbnail=PageThumbnail(source='https://example.com/img.png', width=100, height=100),
        )
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.thumbnail.url == 'https://example.com/img.png'

    def test_no_thumbnail_when_absent(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='text')
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.thumbnail is None

    def test_footer_is_site_name(self):
        from doom_bot.commands.wiki import build_wiki_embed

        summary = PageSummary(title='T', extract='text')
        embed, _ = build_wiki_embed(summary, _SITE_INFO)

        assert embed.footer.text == 'Test Wiki'


# --- /wiki random Command Tests ---


class TestWikiRandomCommand:
    @pytest.mark.asyncio
    async def test_random_responds_with_embed(self, mock_ctx):
        """/wiki random sends a discord embed"""
        from doom_bot.commands.wiki import wiki_random

        summary = PageSummary(title='Random Page', extract='Some intro text.')
        site_info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1', sitename='Test Wiki')

        mock_wiki = MagicMock()
        mock_wiki.pages.get_random_summary = AsyncMock(return_value=summary)
        mock_wiki.search.site_info = AsyncMock(return_value=site_info)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_random(mock_ctx)

        mock_ctx.respond.assert_called_once()
        call_kwargs = mock_ctx._responses[0]['kwargs']
        embed = call_kwargs['embed']
        assert isinstance(embed, discord.Embed)
        assert embed.title == 'Random Page'
        assert embed.description is not None
        assert 'Some intro text.' in embed.description

    @pytest.mark.asyncio
    async def test_random_includes_link_button(self, mock_ctx):
        """/wiki random includes the open wiki link button"""
        from doom_bot.commands.wiki import wiki_random

        summary = PageSummary(title='Random Page', extract='text')
        site_info = SiteInfo(server='https://wiki.example.com', articlepath='/wiki/$1')

        mock_wiki = MagicMock()
        mock_wiki.pages.get_random_summary = AsyncMock(return_value=summary)
        mock_wiki.search.site_info = AsyncMock(return_value=site_info)

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_random(mock_ctx)

        call_kwargs = mock_ctx._responses[0]['kwargs']
        view = call_kwargs['view']
        assert view is not None
        link_buttons = [c for c in view.children if isinstance(c, discord.ui.Button) and c.style == discord.ButtonStyle.link]
        assert len(link_buttons) == 1
        assert link_buttons[0].label == 'Open Wiki!'

    @pytest.mark.asyncio
    async def test_random_defers_before_fetch(self, mock_ctx):
        """/wiki random defers the response before hitting the api"""
        from doom_bot.commands.wiki import wiki_random

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

        async def tracking_respond(*args, **kwargs):
            defer_order.append('respond')
            await original_respond(*args, **kwargs)

        mock_ctx.defer = tracking_defer
        mock_ctx.respond = tracking_respond

        with patch('doom_bot.commands.wiki.get_wiki', return_value=mock_wiki):
            await wiki_random(mock_ctx)

        assert defer_order == ['defer', 'respond']
