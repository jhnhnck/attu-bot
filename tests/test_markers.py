"""
AttuBot - Marker Resolver and YearMarker Model Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests for resolve_marker(), has_year_marker(), and the YearMarker model.
All repository and config access is mocked.
"""

import os
import time as _time

os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.database.models import YearMarkerDocument
from attubot.markers import ResolvedMarker, YearMarker, has_year_marker, resolve_marker
from tests.conftest import TEST_GUILD

TEST_CHANNEL = 666666
TEST_CHANNEL_2 = 777777
TEST_MSG_ID = 123456789012345678
TEST_YEAR = 5

# --- has_year_marker ---


class TestHasYearMarker:
    def test_bot_format_matches(self):
        # matches the output of format_year_line
        assert has_year_marker(5, '# <<< Year 5 PC <<<') is True

    def test_human_style_with_year_keyword(self):
        assert has_year_marker(5, '====== Year 5 PC ======') is True

    def test_human_style_no_year_keyword(self):
        # just a number with no 'year' or 'pc' context - should not match
        assert has_year_marker(5, '====== 5 ======') is False

    def test_pc_only(self):
        assert has_year_marker(3, '--- 3 PC ---') is True

    def test_wrong_year(self):
        assert has_year_marker(5, '# <<< Year 6 PC <<<') is False

    def test_multiline_only_first_line_checked(self):
        # year marker on second line only - should not match
        assert has_year_marker(5, 'just some message\n# <<< Year 5 PC <<<') is False

    def test_case_insensitive(self):
        assert has_year_marker(5, '=== YEAR 5 PC ===') is True

    def test_adjacent_year_for_single_digit(self):
        # year 1 should accept "Year 0" in the line (legacy single-digit tolerance)
        assert has_year_marker(1, '=== year 0 PC ===') is True

    def test_adjacent_year_not_applied_to_large_years(self):
        # year 20 should NOT accept 19 via the adjacency rule (only for year < 10)
        assert has_year_marker(20, '=== year 19 PC ===') is False


# --- ResolvedMarker ---


class TestResolvedMarker:
    def test_found_true_when_message_nonzero(self):
        m = ResolvedMarker(guild=TEST_GUILD, channel=TEST_CHANNEL, year=1, message=TEST_MSG_ID, exact=True, source='bot')
        assert m.found is True

    def test_found_false_when_message_zero(self):
        m = ResolvedMarker(guild=TEST_GUILD, channel=TEST_CHANNEL, year=1, message=0, exact=False, source='none')
        assert m.found is False


# --- resolve_marker ---


def _make_year_marker_doc(channel=TEST_CHANNEL, year=TEST_YEAR, message=TEST_MSG_ID, guild=TEST_GUILD, exact=True):
    return YearMarkerDocument(guild=guild, channel=channel, message=message, year=year, exact=exact)


def _make_year_doc(year=TEST_YEAR, start_time=1_700_000_000, end_time=1_701_000_000):
    from attubot.database.models import YearDocument

    return YearDocument(guild=TEST_GUILD, year=year, start_time=start_time, end_time=end_time, duration=1)


class TestResolveMarkerOverride:
    """Source=override: admin override in year_markers collection takes priority."""

    @pytest.mark.asyncio
    async def test_override_found(self):
        doc = _make_year_marker_doc()
        with patch('attubot.markers._get_repo') as mock_repo_fn:
            repo = AsyncMock()
            repo.get = AsyncMock(return_value=doc)
            mock_repo_fn.return_value = repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'override'
        assert result.message == TEST_MSG_ID
        assert result.exact is True
        assert result.found is True

    @pytest.mark.asyncio
    async def test_override_not_found_falls_through(self, make_year_doc, mock_marker_repo):
        """When no override, resolver proceeds to message-based lookups."""
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_repo_fn, patch('attubot.years.Year') as mock_year_cls:
            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=None)
            msg_repo.find_first_message = AsyncMock(return_value=None)
            mock_msg_repo_fn.return_value = msg_repo

            # give it a year record so the window is valid

            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())

            # patch config for marker authors and lore channels
            with patch('attubot.markers.config') as mock_cfg:
                mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[]), channels=MagicMock(lore_channels=[]))
                result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'none'
        assert result.found is False


class TestResolveMarkerBotHeader:
    """Source=bot: message from bot matching format_year_line."""

    @pytest.mark.asyncio
    async def test_bot_header_found(self, mock_marker_repo):
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[]), channels=MagicMock(lore_channels=[]))

            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=TEST_MSG_ID)
            msg_repo.find_author_message = AsyncMock(return_value=None)
            msg_repo.find_first_message = AsyncMock(return_value=None)
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'bot'
        assert result.message == TEST_MSG_ID
        assert result.exact is True


class TestResolveMarkerAuthorHeader:
    """Source=author: message from an authorized marker author matching has_year_marker."""

    @pytest.mark.asyncio
    async def test_author_header_found(self, mock_marker_repo):
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[999]), channels=MagicMock(lore_channels=[]))

            from attubot.database.models import MessageDocument

            msg_doc = MessageDocument(
                message_id=TEST_MSG_ID,
                guild_id=TEST_GUILD,
                channel_id=TEST_CHANNEL,
                author_id=999,
                author_name='marker-person',
                content=f'=== Year {TEST_YEAR} PC ===',
                created_at=1_700_000_001,
            )
            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=TEST_MSG_ID)
            msg_repo.get = AsyncMock(return_value=msg_doc)
            msg_repo.find_first_message = AsyncMock(return_value=None)
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'author'
        assert result.message == TEST_MSG_ID
        assert result.exact is True

    @pytest.mark.asyncio
    async def test_author_message_content_mismatch_falls_through(self, mock_marker_repo):
        """Author message found but content doesn't look like a year header."""
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[999]), channels=MagicMock(lore_channels=[]))

            from attubot.database.models import MessageDocument

            msg_doc = MessageDocument(
                message_id=TEST_MSG_ID,
                guild_id=TEST_GUILD,
                channel_id=TEST_CHANNEL,
                author_id=999,
                author_name='marker-person',
                content='hello there, nothing to do with years',
                created_at=1_700_000_001,
            )
            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=TEST_MSG_ID)
            msg_repo.get = AsyncMock(return_value=msg_doc)
            msg_repo.find_first_message = AsyncMock(return_value=TEST_MSG_ID + 1)
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        # fell through to 'first' because content didn't match
        assert result.source == 'first'
        assert result.exact is False


class TestResolveMarkerFirstMessage:
    """Source=first: chronologically first message in the year window."""

    @pytest.mark.asyncio
    async def test_first_message_found(self, mock_marker_repo):
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[]), channels=MagicMock(lore_channels=[]))

            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=None)
            msg_repo.find_first_message = AsyncMock(return_value=TEST_MSG_ID)
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'first'
        assert result.message == TEST_MSG_ID
        assert result.exact is False


class TestResolveMarkerPrimaryFallback:
    """Source=primary: no messages in channel, use primary lore channel's marker."""

    @pytest.mark.asyncio
    async def test_primary_fallback_used(self, mock_marker_repo):
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            # target channel has no messages; primary channel is TEST_CHANNEL_2
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[]), channels=MagicMock(lore_channels=[TEST_CHANNEL_2, TEST_CHANNEL]))

            msg_repo = AsyncMock()

            async def first_message_side_effect(guild_id, channel_id, after, before):
                if channel_id == TEST_CHANNEL:
                    return None
                return TEST_MSG_ID + 1

            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=None)
            msg_repo.find_first_message = first_message_side_effect
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'primary'
        assert result.message == TEST_MSG_ID + 1
        assert result.exact is False

    @pytest.mark.asyncio
    async def test_primary_fallback_same_channel_returns_none(self, mock_marker_repo):
        """When the target IS the primary channel and has no messages, result is 'none'."""
        mock_marker_repo.get = AsyncMock(return_value=None)
        mock_marker_repo.get_any_for_guild_year = AsyncMock(return_value=None)

        with patch('attubot.markers._get_message_repo') as mock_msg_fn, patch('attubot.years.Year') as mock_year_cls, patch('attubot.markers.config') as mock_cfg:
            mock_year_cls.get = AsyncMock(return_value=_make_year_doc())
            # target channel is the primary channel
            mock_cfg.guild.return_value = MagicMock(users=MagicMock(markers=[]), channels=MagicMock(lore_channels=[TEST_CHANNEL]))

            msg_repo = AsyncMock()
            msg_repo.find_bot_header = AsyncMock(return_value=None)
            msg_repo.find_author_message = AsyncMock(return_value=None)
            msg_repo.find_first_message = AsyncMock(return_value=None)
            mock_msg_fn.return_value = msg_repo

            result = await resolve_marker(TEST_GUILD, TEST_CHANNEL, TEST_YEAR)

        assert result.source == 'none'
        assert result.found is False


# --- YearMarker model ---


class TestYearMarkerModel:
    @pytest.mark.asyncio
    async def test_get_returns_marker(self, mock_marker_repo):
        doc = _make_year_marker_doc()
        mock_marker_repo.get = AsyncMock(return_value=doc)
        result = await YearMarker.get(TEST_CHANNEL, TEST_YEAR)
        assert result is not None
        assert result.channel == TEST_CHANNEL
        assert result.year == TEST_YEAR
        assert result.exact is True
        mock_marker_repo.get.assert_called_once_with(TEST_CHANNEL, TEST_YEAR)

    @pytest.mark.asyncio
    async def test_get_returns_none(self, mock_marker_repo):
        mock_marker_repo.get = AsyncMock(return_value=None)
        result = await YearMarker.get(TEST_CHANNEL, TEST_YEAR)
        assert result is None

    @pytest.mark.asyncio
    async def test_save_calls_upsert(self, mock_marker_repo):
        marker = YearMarker(guild=TEST_GUILD, channel=TEST_CHANNEL, message=TEST_MSG_ID, year=TEST_YEAR)
        await marker.save()
        mock_marker_repo.upsert.assert_called_once_with(
            guild=TEST_GUILD,
            channel=TEST_CHANNEL,
            message=TEST_MSG_ID,
            year=TEST_YEAR,
            exact=True,
            wiki_page=False,
        )

    @pytest.mark.asyncio
    async def test_delete_calls_repo(self, mock_marker_repo):
        marker = YearMarker(guild=TEST_GUILD, channel=TEST_CHANNEL, message=TEST_MSG_ID, year=TEST_YEAR)
        await marker.delete()
        mock_marker_repo.delete.assert_called_once_with(TEST_CHANNEL, TEST_YEAR)

    @pytest.mark.asyncio
    async def test_mark_stores_override(self, mock_marker_repo, guild):
        await YearMarker.mark(year=TEST_YEAR, message_id=TEST_MSG_ID, channel=TEST_CHANNEL, guild=TEST_GUILD)
        mock_marker_repo.upsert.assert_called_once()
        call_kwargs = mock_marker_repo.upsert.call_args.kwargs
        assert call_kwargs['year'] == TEST_YEAR
        assert call_kwargs['message'] == TEST_MSG_ID
        assert call_kwargs['exact'] is True

    @pytest.mark.asyncio
    async def test_all_for_guild_returns_list(self, mock_marker_repo):
        docs = [_make_year_marker_doc(year=y) for y in range(1, 4)]
        mock_marker_repo.all_for_guild = AsyncMock(return_value=docs)
        result = await YearMarker.all_for_guild(TEST_GUILD)
        assert len(result) == 3
        assert all(isinstance(m, YearMarker) for m in result)
        assert [m.year for m in result] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_exists_true(self, mock_marker_repo):
        mock_marker_repo.exists = AsyncMock(return_value=True)
        assert await YearMarker.exists(TEST_CHANNEL, TEST_YEAR) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, mock_marker_repo):
        mock_marker_repo.exists = AsyncMock(return_value=False)
        assert await YearMarker.exists(TEST_CHANNEL, TEST_YEAR) is False
