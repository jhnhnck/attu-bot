"""
AttuBot - Reminder Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for the reminder feature: fire time computation, date formatting,
and slash command validation.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, patch

import pytest
from freezegun import freeze_time

from attubot.client.calendar import AttuYearSpan
from attubot.database.models import ReminderDocument
from attubot.tasks.reminder import compute_fire_time, format_attu_date
from tests.conftest import test_channel, test_guild, test_user


def _make_reminder(**kwargs) -> ReminderDocument:
    """Create a ReminderDocument with sensible defaults."""
    defaults = {
        'reminder_id': 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee',
        'guild_id': test_guild,
        'user_id': test_user,
        'channel_id': test_channel,
        'attu_year': 5,
        'attu_month': None,
        'attu_day': None,
        'note': '',
        'created_at': 1700000000,
    }
    defaults.update(kwargs)
    return ReminderDocument(**defaults)


# --- format_attu_date ---


class TestFormatAttuDate:
    def test_year_only(self):
        r = _make_reminder(attu_year=5, attu_month=None, attu_day=None)
        assert format_attu_date(r) == 'Year 5 PC'

    def test_year_and_month(self):
        r = _make_reminder(attu_year=5, attu_month=3, attu_day=None)
        assert format_attu_date(r) == 'month 3, Year 5 PC'

    def test_year_month_and_day(self):
        r = _make_reminder(attu_year=5, attu_month=3, attu_day=15)
        assert format_attu_date(r) == '15-3 5 PC'

    def test_first_day_of_year(self):
        r = _make_reminder(attu_year=1, attu_month=1, attu_day=1)
        assert format_attu_date(r) == '1-1 1 PC'

    def test_last_day_of_year(self):
        r = _make_reminder(attu_year=10, attu_month=12, attu_day=30)
        assert format_attu_date(r) == '30-12 10 PC'


# --- compute_fire_time ---


class TestComputeFireTime:
    @pytest.mark.asyncio
    async def test_year_only_fires_at_start(self, guild):
        """Year-only reminder fires at the start_time of the year span."""
        span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span):
            r = _make_reminder(attu_year=5, attu_month=None)
            result = await compute_fire_time(r)

        assert result is not None
        assert int(result.timestamp()) == 1704067200

    @pytest.mark.asyncio
    async def test_year_and_month_interpolation(self, guild):
        """Year+month reminder fires at the start of that month within the span."""
        # 14-day year: span_seconds = 1209600
        span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span):
            # month 3 (no day) → haracalnde_pos = (3-1)*30 + (1-1) = 60
            r = _make_reminder(attu_year=5, attu_month=3, attu_day=None)
            result = await compute_fire_time(r)

        assert result is not None
        expected_ts = 1704067200 + (60 / 360) * (1705276800 - 1704067200)
        assert abs(result.timestamp() - expected_ts) < 1

    @pytest.mark.asyncio
    async def test_year_month_day_interpolation(self, guild):
        """Full date reminder fires at the correct interpolated position."""
        span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span):
            # 15-3 → haracalnde_pos = (3-1)*30 + (15-1) = 74
            r = _make_reminder(attu_year=5, attu_month=3, attu_day=15)
            result = await compute_fire_time(r)

        assert result is not None
        expected_ts = 1704067200 + (74 / 360) * (1705276800 - 1704067200)
        assert abs(result.timestamp() - expected_ts) < 1

    @pytest.mark.asyncio
    async def test_paused_guild_returns_none(self, make_guild):
        """Paused guild → cannot compute fire time."""
        make_guild(paused=True)
        r = _make_reminder(attu_year=5)
        result = await compute_fire_time(r)
        assert result is None

    @pytest.mark.asyncio
    async def test_unauthorized_guild_returns_none(self):
        """Guild not in config → returns None."""
        r = _make_reminder(guild_id=9999999999, attu_year=5)
        result = await compute_fire_time(r)
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_span_returns_none(self, guild):
        """Invalid span (start/end = 0) → returns None."""
        span = AttuYearSpan(start_time=0, end_time=0, duration=0)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span):
            r = _make_reminder(attu_year=5)
            result = await compute_fire_time(r)

        assert result is None


# --- /remind add validation ---


class TestRemindAddValidation:
    @pytest.mark.asyncio
    async def test_day_without_month_rejected(self, mock_ctx, guild):
        """Day without month should be rejected."""
        from attubot.commands.remind import remind_add

        await remind_add(mock_ctx, year=5, month=None, day=15)

        mock_ctx.respond.assert_called_once()
        args = mock_ctx._responses[0]
        assert 'day requires a month' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    async def test_paused_guild_rejected(self, mock_ctx, make_guild):
        """Reminders should be rejected when time is paused."""
        from attubot.commands.remind import remind_add

        make_guild(paused=True)
        await remind_add(mock_ctx, year=5)

        mock_ctx.respond.assert_called_once()
        args = mock_ctx._responses[0]
        assert 'time is paused' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    @freeze_time('2024-02-01 12:00:00')
    async def test_past_date_rejected(self, mock_ctx, guild):
        """Reminders for past dates should be rejected."""
        from attubot.commands.remind import remind_add

        # year 1 starts at epoch (2024-01-01) which is in the past
        span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span):
            await remind_add(mock_ctx, year=1)

        mock_ctx.respond.assert_called_once()
        args = mock_ctx._responses[0]
        assert 'already passed' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    @freeze_time('2024-01-02 12:00:00')
    async def test_future_date_accepted(self, mock_ctx, guild):
        """Valid future date should insert and respond with confirmation."""
        from attubot.commands.remind import remind_add

        # year 5 is well in the future
        span = AttuYearSpan(start_time=1708000000, end_time=1709209600, duration=14)

        mock_repo = AsyncMock()
        mock_interaction_msg = AsyncMock()
        mock_interaction_msg.id = 1111111111
        mock_ctx.interaction.original_response = AsyncMock(return_value=mock_interaction_msg)

        with patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span), patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            await remind_add(mock_ctx, year=5, note='test note')

        # should have inserted a reminder
        mock_repo.insert.assert_called_once()
        doc = mock_repo.insert.call_args[0][0]
        assert doc.attu_year == 5
        assert doc.note == 'test note'

        # should have responded with confirmation
        assert len(mock_ctx._responses) == 1
        response = mock_ctx._responses[0]['args'][0]
        assert 'reminder set for' in response
        assert 'Year 5 PC' in response


# --- /remind cancel validation ---


class TestRemindCancelValidation:
    @pytest.mark.asyncio
    async def test_cancel_other_users_reminder_rejected(self, mock_ctx, guild):
        """Cannot cancel another user's reminder."""
        from attubot.commands.remind import remind_cancel

        other_user_reminder = _make_reminder(user_id=1111111111)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = other_user_reminder
        mock_repo.get_by_prefix.return_value = None

        with patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            await remind_cancel(mock_ctx, reminder_id=other_user_reminder.reminder_id)

        args = mock_ctx._responses[0]
        assert 'belongs to someone else' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_reminder_rejected(self, mock_ctx, guild):
        """Cancelling a nonexistent reminder should fail."""
        from attubot.commands.remind import remind_cancel

        mock_repo = AsyncMock()
        mock_repo.get.return_value = None
        mock_repo.get_by_prefix.return_value = None

        with patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            await remind_cancel(mock_ctx, reminder_id='nonexistent')

        args = mock_ctx._responses[0]
        assert 'not found' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    async def test_cancel_fired_reminder_rejected(self, mock_ctx, guild):
        """Cannot cancel an already-fired reminder."""
        from attubot.commands.remind import remind_cancel

        fired_reminder = _make_reminder(user_id=test_user, fired=True, fired_at=1700000000)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = fired_reminder
        mock_repo.get_by_prefix.return_value = None

        with patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            await remind_cancel(mock_ctx, reminder_id=fired_reminder.reminder_id)

        args = mock_ctx._responses[0]
        assert 'already fired' in args['args'][0]
        assert args['kwargs'].get('ephemeral') is True

    @pytest.mark.asyncio
    async def test_cancel_own_reminder_succeeds(self, mock_ctx, guild):
        """Owner can cancel their own reminder."""
        from attubot.commands.remind import remind_cancel

        reminder = _make_reminder(user_id=test_user)
        mock_repo = AsyncMock()
        mock_repo.get.return_value = reminder
        mock_repo.delete.return_value = True

        with patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            await remind_cancel(mock_ctx, reminder_id=reminder.reminder_id)

        mock_repo.delete.assert_called_once_with(reminder.reminder_id)
        response = mock_ctx._responses[0]['args'][0]
        assert 'cancelled' in response
