"""
AttuBot - Time Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for /time advance, /time pause, /time resume, and /time dilate commands from time.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import test_guild


# --- /time advance Command Tests ---


class TestTimeAdvanceCommand:
    @pytest.mark.asyncio
    async def test_advance_with_existing_year(self, mock_ctx, guild):
        """test /time advance forces year advance using latest year from db

        note: the source uses cfg.guild.id which is a latent bug (GuildConfig
        has .id, not .guild); we mock config.guild() to return a MagicMock so
        the attribute chain resolves without error.
        """
        from attubot.commands.time import time_advance

        mock_year = MagicMock()
        mock_year.year = 5

        mock_coro = AsyncMock()()
        mock_cfg = MagicMock()
        mock_cfg.guild.id = test_guild

        with patch('attubot.commands.time.Year') as mock_year_cls, patch('attubot.commands.time.get_year_status', return_value=(10, 5)), patch('attubot.commands.time.scheduler') as mock_scheduler, patch('attubot.commands.time.nova_year_task') as mock_nova, patch('attubot.commands.time.config') as mock_config:
            mock_config.guild.return_value = mock_cfg
            mock_year_cls.get_latest = AsyncMock(return_value=mock_year)
            mock_scheduler.add_job = MagicMock()
            mock_nova._advance_year = MagicMock(return_value=mock_coro)

            await time_advance(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'forcing new year' in response.lower()

        # forced_year should be latest_year.year + 1 = 6
        mock_nova._advance_year.assert_called_once()
        advance_call = mock_nova._advance_year.call_args
        assert advance_call[0][0] is mock_cfg  # cfg
        assert advance_call[0][1] == 6  # forced_year = 5 + 1

        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args
        assert call_args[0][1] == 'ManualYearAdvance'
        assert call_args[0][2] == test_guild

    @pytest.mark.asyncio
    async def test_advance_with_no_existing_year(self, mock_ctx, guild):
        """test /time advance when no year exists in db starts from year 1"""
        from attubot.commands.time import time_advance

        mock_coro = AsyncMock()()
        mock_cfg = MagicMock()
        mock_cfg.guild.id = test_guild

        with patch('attubot.commands.time.Year') as mock_year_cls, patch('attubot.commands.time.get_year_status', return_value=(0, 1)), patch('attubot.commands.time.scheduler') as mock_scheduler, patch('attubot.commands.time.nova_year_task') as mock_nova, patch('attubot.commands.time.config') as mock_config:
            mock_config.guild.return_value = mock_cfg
            mock_year_cls.get_latest = AsyncMock(return_value=None)
            mock_scheduler.add_job = MagicMock()
            mock_nova._advance_year = MagicMock(return_value=mock_coro)

            await time_advance(mock_ctx)

        mock_ctx.respond.assert_called_once()
        mock_scheduler.add_job.assert_called_once()

        # with no existing year, forced_year should be 0 + 1 = 1
        advance_call = mock_nova._advance_year.call_args
        assert advance_call[0][1] == 1


# --- /time pause Command Tests ---


class TestTimePauseCommand:
    @pytest.mark.asyncio
    async def test_pause(self, mock_ctx, guild):
        """test /time pause pauses the epoch"""
        from attubot.commands.time import time_pause

        with patch('attubot.config.GuildConfig.pause_time', new_callable=AsyncMock) as mock_pause:
            await time_pause(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'stopped' in response.lower()
        mock_pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_pause_response_before_action(self, mock_ctx, guild):
        """test /time pause responds to user before pausing"""
        from attubot.commands.time import time_pause

        call_order = []

        async def track_respond(*args, **kwargs):
            call_order.append('respond')

        async def track_pause():
            call_order.append('pause')

        mock_ctx.respond = AsyncMock(side_effect=track_respond)

        with patch('attubot.config.GuildConfig.pause_time', new_callable=AsyncMock, side_effect=track_pause):
            await time_pause(mock_ctx)

        assert call_order == ['respond', 'pause']


# --- /time resume Command Tests ---


class TestTimeResumeCommand:
    @pytest.mark.asyncio
    async def test_resume(self, mock_ctx, guild):
        """test /time resume resumes the epoch and responds with year info"""
        from attubot.commands.time import time_resume

        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock) as mock_move, patch('attubot.config.GuildConfig.resume_time', new_callable=AsyncMock) as mock_resume:
            await time_resume(mock_ctx)

        mock_move.assert_called_once()
        # move_epoch should be called with the guild's epoch length and guild id
        call_kwargs = mock_move.call_args
        assert call_kwargs[0][0] == guild.epoch.length
        assert call_kwargs[1]['guild'] == test_guild

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'resumed' in response.lower()
        assert 'PC' in response

        mock_resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_calls_move_epoch_before_respond(self, mock_ctx, guild):
        """test /time resume calls move_epoch before responding"""
        from attubot.commands.time import time_resume

        call_order = []

        async def track_move(*args, **kwargs):
            call_order.append('move_epoch')

        async def track_respond(*args, **kwargs):
            call_order.append('respond')

        async def track_resume():
            call_order.append('resume')

        mock_ctx.respond = AsyncMock(side_effect=track_respond)

        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock, side_effect=track_move), patch('attubot.config.GuildConfig.resume_time', new_callable=AsyncMock, side_effect=track_resume):
            await time_resume(mock_ctx)

        assert call_order == ['move_epoch', 'respond', 'resume']


# --- /time dilate Command Tests ---


class TestTimeDilateCommand:
    @pytest.mark.asyncio
    async def test_dilate_not_divisible_by_7(self, mock_ctx, guild):
        """test /time dilate rejects values not divisible by 7"""
        from attubot.commands.time import time_dilate

        await time_dilate(mock_ctx, days=10)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'failed' in response.lower()
        assert 'divisible by 7' in response.lower()

    @pytest.mark.asyncio
    async def test_dilate_not_divisible_by_7_other_values(self, mock_ctx, guild):
        """test /time dilate rejects various non-divisible-by-7 inputs"""
        from attubot.commands.time import time_dilate

        for bad_days in [1, 2, 3, 8, 13, 15, 20, 22]:
            mock_ctx._responses.clear()
            mock_ctx.respond.reset_mock()

            await time_dilate(mock_ctx, days=bad_days)

            mock_ctx.respond.assert_called_once()
            response = mock_ctx._responses[0]['args'][0]
            assert 'divisible by 7' in response.lower(), f'days={bad_days} should be rejected'

    @pytest.mark.asyncio
    async def test_dilate_valid_paused(self, mock_ctx, make_guild):
        """test /time dilate with valid input when time is paused sets year length"""
        from attubot.commands.time import time_dilate

        make_guild(paused=True)

        with patch('attubot.config.GuildConfig.set_year_length', new_callable=AsyncMock) as mock_set:
            await time_dilate(mock_ctx, days=21)

        mock_set.assert_called_once_with(21)
        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'days per year' in response

    @pytest.mark.asyncio
    async def test_dilate_valid_not_paused(self, mock_ctx, guild):
        """test /time dilate with valid input when time is not paused calls move_epoch"""
        from attubot.commands.time import time_dilate

        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock) as mock_move:
            await time_dilate(mock_ctx, days=28)

        mock_move.assert_called_once_with(28, guild=test_guild)
        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'days per year' in response
        assert 'epoch at' in response

    @pytest.mark.asyncio
    async def test_dilate_7_days(self, mock_ctx, guild):
        """test /time dilate with minimum valid input of 7 days"""
        from attubot.commands.time import time_dilate

        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock):
            await time_dilate(mock_ctx, days=7)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'days per year' in response

    @pytest.mark.asyncio
    async def test_dilate_zero_days_skips_validation(self, mock_ctx, guild):
        """test /time dilate with 0 days bypasses the divisible-by-7 check"""
        from attubot.commands.time import time_dilate

        # days=0 is not > 0, so it skips the mod-7 guard
        # but epoch is not paused, so it goes to move_epoch branch
        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock):
            await time_dilate(mock_ctx, days=0)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        # should not show the failure message
        assert 'failed' not in response.lower()

    @pytest.mark.asyncio
    async def test_dilate_negative_days_skips_validation(self, mock_ctx, guild):
        """test /time dilate with negative days bypasses the divisible-by-7 check"""
        from attubot.commands.time import time_dilate

        # negative days are not > 0, so they skip the mod-7 guard
        with patch('attubot.commands.time.move_epoch', new_callable=AsyncMock):
            await time_dilate(mock_ctx, days=-7)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'failed' not in response.lower()
