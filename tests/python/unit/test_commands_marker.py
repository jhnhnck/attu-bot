# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_commands_marker | tests for /marker save, set, and clear commands."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nova_core.client.markers import YearMarker
from tests.conftest import test_guild


test_lore_channel = 4444444444
test_other_channel = 5555555555

# two snowflakes whose timestamps are close (~60s apart)
_snowflake_a = 1200000000000000000
_snowflake_b = 1200000252000000000  # ~60s later via discord snowflake formula


# --- helpers ---


def _guild_config(current_year=10, lore_channels=None):
    """build a mock guild config with lore channels set"""
    cfg = MagicMock()
    cfg.id = test_guild
    cfg.channels = MagicMock()
    cfg.channels.lore_channels = lore_channels if lore_channels is not None else [test_lore_channel]
    return cfg


def _patch_config_and_year_status(current_year=10, guild_cfg=None):
    """returns a tuple of patches for config.guild and get_year_status"""
    if guild_cfg is None:
        guild_cfg = _guild_config(current_year=current_year)
    return (
        patch('nova_core.commands.marker.config.guild', return_value=guild_cfg),
        patch('nova_core.commands.marker.get_year_status', return_value=(0, current_year)),
    )


def _make_marker(channel=test_lore_channel, year=5, message=_snowflake_a, guild=test_guild, exact=True):
    return YearMarker(guild=guild, channel=channel, message=message, year=year, exact=exact)


# --- /marker save ---


class TestMarkerSave:
    @pytest.mark.asyncio
    async def test_invalid_link_ephemeral(self, mock_ctx):
        """link without discord.com/channels sends ephemeral error"""
        from nova_core.commands.marker import marker_save

        await marker_save(mock_ctx, year=5, link='https://example.com/not-discord', force=False)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'does not look like a discord message link' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_invalid_year_ephemeral(self, mock_ctx):
        """year >= current_year sends ephemeral error"""
        from nova_core.commands.marker import marker_save

        link = f'https://discord.com/channels/{test_guild}/{test_lore_channel}/{_snowflake_a}'
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        with p_guild, p_year:
            await marker_save(mock_ctx, year=10, link=link, force=False)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'only years 1 PC through' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_not_lore_channel_ephemeral(self, mock_ctx):
        """link pointing to a non-lore channel sends ephemeral error"""
        from nova_core.commands.marker import marker_save

        link = f'https://discord.com/channels/{test_guild}/{test_other_channel}/{_snowflake_a}'
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        with p_guild, p_year:
            await marker_save(mock_ctx, year=5, link=link, force=False)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert "isn't a lore channel" in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_time_diff_too_large_without_force(self, mock_ctx):
        """large time diff with force=False sends ephemeral error"""
        from nova_core.commands.marker import marker_save

        link = f'https://discord.com/channels/{test_guild}/{test_lore_channel}/{_snowflake_b}'
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        est_marker = _make_marker(message=_snowflake_a)
        # make the two snowflakes far apart
        far_time = datetime(2020, 1, 1, tzinfo=UTC)
        near_time = datetime(2025, 1, 1, tzinfo=UTC)

        with (
            p_guild,
            p_year,
            patch('nova_core.commands.marker.YearMarker.get', new_callable=AsyncMock, return_value=est_marker),
            patch('nova_core.commands.marker.snowflake_time', side_effect=[far_time, near_time]),
        ):
            await marker_save(mock_ctx, year=5, link=link, force=False)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'seconds off from expected' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_with_force(self, mock_ctx):
        """large time diff with force=True saves successfully"""
        from nova_core.commands.marker import marker_save

        link = f'https://discord.com/channels/{test_guild}/{test_lore_channel}/{_snowflake_b}'
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        est_marker = _make_marker(message=_snowflake_a)
        created_marker = MagicMock()
        created_marker.channel = test_lore_channel
        created_marker.message = _snowflake_b
        created_marker.update = AsyncMock()

        far_time = datetime(2020, 1, 1, tzinfo=UTC)
        near_time = datetime(2025, 1, 1, tzinfo=UTC)

        with (
            p_guild,
            p_year,
            patch('nova_core.commands.marker.YearMarker.get', new_callable=AsyncMock, return_value=est_marker),
            patch('nova_core.commands.marker.snowflake_time', side_effect=[far_time, near_time]),
            patch('nova_core.commands.marker.YearMarker.get_or_create', new_callable=AsyncMock, return_value=(created_marker, True)),
            patch('nova_core.commands.marker.format_message_link', return_value='https://discord.com/channels/1/2/3'),
        ):
            await marker_save(mock_ctx, year=5, link=link, force=True)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Created' in response
        assert 'marker for 5 PC' in response
        created_marker.update.assert_called_once()


# --- /marker set ---


class TestMarkerSet:
    @pytest.mark.asyncio
    async def test_invalid_year_ephemeral(self, mock_ctx):
        """year >= current_year sends ephemeral error"""
        from nova_core.commands.marker import marker_set

        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        with p_guild, p_year:
            await marker_set(mock_ctx, year=10, snowflake=_snowflake_a)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'only years 1 PC through' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_shows_time_adjustment(self, mock_ctx):
        """valid inputs show old and new timestamps in response"""
        from nova_core.commands.marker import marker_set

        p_guild, p_year = _patch_config_and_year_status(current_year=10)
        est_marker = MagicMock()
        est_marker.message = _snowflake_a
        est_marker.update = AsyncMock()

        old_time = datetime(2024, 6, 1, tzinfo=UTC)
        new_time = datetime(2024, 6, 15, tzinfo=UTC)

        with (
            p_guild,
            p_year,
            patch('nova_core.commands.marker.YearMarker.get_any', new_callable=AsyncMock, return_value=est_marker),
            patch('nova_core.commands.marker.snowflake_time', side_effect=[old_time, new_time]),
        ):
            await marker_set(mock_ctx, year=5, snowflake=_snowflake_b)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        # response contains discord timestamp format <t:UNIX:d>
        assert 'adjusted' in response
        assert f'<t:{int(old_time.timestamp())}:d>' in response
        assert f'<t:{int(new_time.timestamp())}:d>' in response
        est_marker.update.assert_called_once()


# --- /marker clear ---


class TestMarkerClear:
    @pytest.mark.asyncio
    async def test_marker_not_found_ephemeral(self, mock_ctx):
        """clearing a nonexistent marker sends ephemeral error"""
        from nova_core.commands.marker import marker_clear

        mock_channel = MagicMock()
        mock_channel.id = test_lore_channel
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        with (
            p_guild,
            p_year,
            patch('nova_core.commands.marker.YearMarker.get', new_callable=AsyncMock, return_value=None),
        ):
            await marker_clear(mock_ctx, year=5, channel=mock_channel)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert "there's no marker for 5 PC" in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_clears_and_responds(self, mock_ctx):
        """clearing an existing marker deletes it and confirms"""
        from nova_core.commands.marker import marker_clear

        mock_channel = MagicMock()
        mock_channel.id = test_lore_channel

        marker = MagicMock()
        marker.delete = AsyncMock()
        p_guild, p_year = _patch_config_and_year_status(current_year=10)

        with (
            p_guild,
            p_year,
            patch('nova_core.commands.marker.YearMarker.get', new_callable=AsyncMock, return_value=marker),
        ):
            await marker_clear(mock_ctx, year=5, channel=mock_channel)

        marker.delete.assert_called_once()
        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'cleared' in response
        assert '5 PC' in response
        # should not be ephemeral (success)
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is not True
