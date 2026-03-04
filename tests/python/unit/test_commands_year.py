"""
AttuBot - Year Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for /year check, /year search, and /year link commands from year.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord.enums import ChannelType
from freezegun import freeze_time

from tests.conftest import TEST_GUILD


# --- /year check Command Tests ---


class TestYearCheckCommand:
    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_prior_year(self, mock_ctx, guild):
        """Test /year check for a prior year shows duration and dates"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        # Mock get_year_span to return a completed year
        mock_span_obj = AttuYearSpan(
            start_time=1704067200,  # 2024-01-01
            end_time=1705276800,  # 2024-01-15
            duration=14,
        )

        # Current year is 2, so year 1 is prior
        # Also need to patch Year.get to avoid database access
        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 2)), patch('attubot.years.Year.get', new_callable=AsyncMock, return_value=None):
            await year_check(mock_ctx, year=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Year 1 PC lasted for 14 days' in response
        assert 'starting on' in response
        assert 'ending on' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_current_year(self, mock_ctx, guild):
        """Test /year check for current year shows will last/started/will end"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        mock_span_obj = AttuYearSpan(
            start_time=1704067200,
            end_time=1705276800,
            duration=14,
        )

        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
            await year_check(mock_ctx, year=2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Year 2 PC will last for 14 days' in response
        assert 'which started on' in response
        assert 'will end on' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-14 16:00:00')  # Day before boundary
    async def test_check_next_year_approaching(self, mock_ctx, guild):
        """Test /year check for next year when approaching (not at boundary yet)"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        mock_span_obj = AttuYearSpan(
            start_time=1705276800,
            end_time=1706486400,
            duration=14,
        )

        # 13 days elapsed (not at boundary), current year 1, checking year 2
        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(13, 1)):
            await year_check(mock_ctx, year=2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        # Should show "Advancing to Year 2 PC" but not "Happy New Year!" (not at boundary)
        assert 'Advancing to Year 2 PC' in response
        assert 'Happy New Year!' not in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_next_year_normal(self, mock_ctx, guild):
        """Test /year check for next year (not at boundary)"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        mock_span_obj = AttuYearSpan(
            start_time=1705276800,
            end_time=1706486400,
            duration=14,
        )

        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 1)):
            await year_check(mock_ctx, year=2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Advancing to Year 2 PC' in response
        assert 'Happy New Year!' not in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_far_future_year(self, mock_ctx, guild):
        """Test /year check for year >80 years away shows easter egg"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        mock_span_obj = AttuYearSpan(start_time=999999999, end_time=0, duration=0)

        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 1)):
            await year_check(mock_ctx, year=3000)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert "we'll all be dead" in response
        assert 'try something sooner' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_future_year(self, mock_ctx, guild):
        """Test /year check for a future year shows start date"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_check

        mock_span_obj = AttuYearSpan(
            start_time=1706486400,
            end_time=1707696000,
            duration=14,
        )

        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 1)):
            await year_check(mock_ctx, year=3)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Year 3 PC will start on' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_check_paused_time(self, mock_ctx, make_guild):
        """Test /year check when time is paused"""
        from attubot.commands.year import year_check

        make_guild(paused=True)

        await year_check(mock_ctx, year=2)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'cancelled' in response or 'paused' in response.lower()

    @pytest.mark.asyncio
    async def test_check_invalid_year(self, mock_ctx, guild):
        """Test /year check with year <= 0 shows error"""
        from attubot.commands.year import year_check

        await year_check(mock_ctx, year=0)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
        assert 'valid' in response.lower()


# --- /year search Command Tests ---


class TestYearSearchCommand:
    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_search_normal_year(self, mock_ctx, make_guild):
        """Test /year search generates proper search query"""
        from attubot.calendar import AttuYearSpan
        from attubot.commands.year import year_search

        cfg = make_guild()
        # Add some channels to config
        cfg.channels.lore_channels = [100, 200]
        cfg.channels.canon_channels = [300]
        cfg.channels.meta_chat = 400

        # Mock the channels - need to properly set the name attribute
        def mock_get_channel(cid):
            mock = MagicMock()
            mock.name = f'channel-{cid}'
            return mock

        mock_ctx.guild.get_channel = MagicMock(side_effect=mock_get_channel)

        mock_span_obj = AttuYearSpan(
            start_time=1704067200,
            end_time=1705276800,
            duration=14,
        )

        with patch('attubot.commands.year.get_year_span', new_callable=AsyncMock, return_value=mock_span_obj), patch('attubot.commands.year.get_year_status', return_value=(7, 1)):
            await year_search(mock_ctx, year=1)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Year 1 PC' in response
        assert 'in:channel-100' in response
        assert 'in:channel-200' in response
        assert 'in:channel-300' in response
        assert 'in:channel-400' in response
        assert 'after:' in response
        assert 'before:' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_search_far_future_year(self, mock_ctx, guild):
        """Test /year search for far future year shows easter egg"""
        from attubot.commands.year import year_search

        with patch('attubot.commands.year.get_year_status', return_value=(7, 1)):
            await year_search(mock_ctx, year=1000)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'timeline isn' in response or 'caught up' in response

    @pytest.mark.asyncio
    async def test_search_invalid_year(self, mock_ctx, guild):
        """Test /year search with year <= 0 shows error"""
        from attubot.commands.year import year_search

        await year_search(mock_ctx, year=0)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
        assert 'valid' in response.lower()


# --- /year link Command Tests ---


class TestYearLinkCommand:
    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_link_valid_year_and_channel(self, mock_ctx, make_guild):
        """Test /year link with valid year and channel"""
        from attubot.commands.year import year_link

        cfg = make_guild()
        cfg.channels.lore_channels = [TEST_GUILD + 100]

        # Mock channel
        mock_channel = MagicMock()
        mock_channel.id = TEST_GUILD + 100
        mock_channel.type = ChannelType.text
        mock_ctx.guild.get_channel_or_thread = MagicMock(return_value=mock_channel)

        # Mock find_marker_link
        with patch('attubot.commands.year.find_marker_link') as mock_find:
            mock_find.return_value = 'https://discord.com/channels/123/456/789'

            with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
                await year_link(mock_ctx, year=1, channel=mock_channel)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert '1 PC:' in response
        assert 'https://discord.com/channels/' in response

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_link_default_channel(self, mock_ctx, make_guild):
        """Test /year link without channel uses first lore channel"""
        from attubot.commands.year import year_link

        cfg = make_guild()
        cfg.channels.lore_channels = [TEST_GUILD + 100]

        # Mock channel
        mock_channel = MagicMock()
        mock_channel.id = TEST_GUILD + 100
        mock_channel.type = ChannelType.text
        mock_ctx.guild.get_channel_or_thread = MagicMock(return_value=mock_channel)

        with patch('attubot.commands.year.find_marker_link') as mock_find:
            mock_find.return_value = 'https://discord.com/channels/123/456/789'

            with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
                await year_link(mock_ctx, year=1, channel=None)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert '1 PC:' in response
        assert 'https://discord.com/channels/' in response

    @pytest.mark.asyncio
    async def test_link_invalid_year_too_low(self, mock_ctx, guild):
        """Test /year link with year < 1 shows error"""
        from attubot.commands.year import year_link

        with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
            await year_link(mock_ctx, year=0, channel=None)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
        assert 'valid' in response.lower()

    @pytest.mark.asyncio
    async def test_link_invalid_year_too_high(self, mock_ctx, guild):
        """Test /year link with year > current shows error"""
        from attubot.commands.year import year_link

        with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
            await year_link(mock_ctx, year=10, channel=None)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
        assert 'valid' in response.lower()

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_link_non_lore_channel(self, mock_ctx, make_guild):
        """Test /year link with non-lore channel shows error"""
        from attubot.commands.year import year_link

        cfg = make_guild()
        cfg.channels.lore_channels = [TEST_GUILD + 100]

        # Mock channel that's NOT in lore channels
        mock_channel = MagicMock()
        mock_channel.id = TEST_GUILD + 999
        mock_channel.type = ChannelType.text
        mock_channel.mention = '#bad-channel'

        with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
            await year_link(mock_ctx, year=1, channel=mock_channel)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
        assert 'lore channel' in response.lower()

    @pytest.mark.asyncio
    @freeze_time('2024-01-08 12:00:00')
    async def test_link_non_text_channel(self, mock_ctx, make_guild):
        """Test /year link with non-text channel shows error"""
        from attubot.commands.year import year_link

        cfg = make_guild()
        cfg.channels.lore_channels = [TEST_GUILD + 100]

        # Mock voice channel
        mock_channel = MagicMock()
        mock_channel.id = TEST_GUILD + 100
        mock_channel.type = ChannelType.voice
        mock_channel.mention = '#voice-channel'

        with patch('attubot.commands.year.get_year_status', return_value=(7, 2)):
            await year_link(mock_ctx, year=1, channel=mock_channel)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Failed' in response
