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

from unittest.mock import AsyncMock, MagicMock, patch

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
        assert format_attu_date(r) == '5 PC'

    def test_year_and_month(self):
        r = _make_reminder(attu_year=5, attu_month=3, attu_day=None)
        assert format_attu_date(r) == '1-3 5 PC'

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
        assert 'must be in the future' in args['args'][0]
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

        # should have responded with an embed confirmation
        assert len(mock_ctx._responses) == 1
        embed = mock_ctx._responses[0]['kwargs']['embed']
        assert embed.title == 'reminder'
        assert '5 PC' in embed.description
        assert 'test note' in embed.description

    @pytest.mark.asyncio
    @freeze_time('2024-01-02 12:00:00')
    async def test_future_date_wakes_reminder_task(self, mock_ctx, guild):
        """Successful insert should call request_wake() on the reminder task."""
        from attubot.commands.remind import remind_add

        span = AttuYearSpan(start_time=1708000000, end_time=1709209600, duration=14)

        mock_repo = AsyncMock()
        mock_interaction_msg = AsyncMock()
        mock_interaction_msg.id = 1111111111
        mock_ctx.interaction.original_response = AsyncMock(return_value=mock_interaction_msg)

        with (
            patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=span),
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.commands.remind.reminder_task') as mock_task,
        ):
            await remind_add(mock_ctx, year=5)

        mock_task.request_wake.assert_called_once()


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
        assert 'already been reminded' in args['args'][0]
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


# --- _deliver_reminder ---


class TestDeliverReminder:
    @pytest.mark.asyncio
    async def test_happy_path_sends_to_original_channel(self, guild):
        """delivers the reminder embed to the original channel with a user mention."""
        from attubot.tasks.reminder import _deliver_reminder

        reminder = _make_reminder(attu_year=5, attu_month=3, attu_day=15, note='do the thing')

        mock_channel = AsyncMock()
        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=mock_channel)

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await _deliver_reminder(reminder)

        mock_channel.send.assert_called_once()
        kwargs = mock_channel.send.call_args.kwargs
        assert f'<@{test_user}>' in kwargs['content']
        embed = kwargs['embed']
        assert embed.title == 'reminder'
        assert '15-3 5 PC' in embed.description
        assert 'do the thing' in embed.description

    @pytest.mark.asyncio
    async def test_fallback_to_meta_chat(self, make_guild):
        """falls back to meta_chat when the original channel is not found."""
        from attubot.tasks.reminder import _deliver_reminder

        cfg = make_guild()
        meta_channel_id = 7777777777
        cfg.channels.meta_chat = meta_channel_id

        reminder = _make_reminder(attu_year=5)

        mock_meta_channel = AsyncMock()
        mock_guild = MagicMock()

        def _get_channel(cid):
            if cid == meta_channel_id:
                return mock_meta_channel
            return None

        mock_guild.get_channel_or_thread = MagicMock(side_effect=_get_channel)

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await _deliver_reminder(reminder)

        mock_meta_channel.send.assert_called_once()

    @pytest.mark.asyncio
    async def test_guild_not_found(self):
        """logs warning and returns when guild is not found."""
        from attubot.tasks.reminder import _deliver_reminder

        reminder = _make_reminder()

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = None
            # should not raise
            await _deliver_reminder(reminder)

    @pytest.mark.asyncio
    async def test_no_channel_at_all(self, make_guild):
        """logs warning when neither original channel nor meta_chat is found."""
        from attubot.tasks.reminder import _deliver_reminder

        cfg = make_guild()
        cfg.channels.meta_chat = 0  # no meta chat configured

        reminder = _make_reminder()

        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=None)

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            # should not raise
            await _deliver_reminder(reminder)

    @pytest.mark.asyncio
    async def test_includes_message_link(self, guild):
        """includes a jump url in the embed when the reminder has a message_id."""
        from attubot.tasks.reminder import _deliver_reminder

        reminder = _make_reminder(attu_year=5, message_id=1234567890)

        mock_channel = AsyncMock()
        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=mock_channel)

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await _deliver_reminder(reminder)

        embed = mock_channel.send.call_args.kwargs['embed']
        assert 'discord.com/channels' in embed.description

    @pytest.mark.asyncio
    async def test_no_note_no_message_id(self, guild):
        """embed has no note line and no jump url when both are absent."""
        from attubot.tasks.reminder import _deliver_reminder

        reminder = _make_reminder(attu_year=5, note='', message_id=0)

        mock_channel = AsyncMock()
        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=mock_channel)

        with patch('attubot.tasks.reminder.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await _deliver_reminder(reminder)

        kwargs = mock_channel.send.call_args.kwargs
        assert f'<@{test_user}>' in kwargs['content']
        embed = kwargs['embed']
        assert '5 PC' in embed.description
        # no note or link appended
        assert '\n>' not in embed.description
        assert 'discord.com/channels' not in embed.description


# --- ReminderTask.run ---


class TestReminderTaskRun:
    @pytest.mark.asyncio
    async def test_fires_overdue_reminders(self, guild):
        """run() fires reminders whose fire time is in the past and marks them fired."""
        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        reminder = _make_reminder(attu_year=1, attu_month=1, attu_day=1)
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[reminder])

        # fire time in the past
        past_span = AttuYearSpan(start_time=1000000, end_time=1200000, duration=14)

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=past_span),
            patch('attubot.tasks.reminder._deliver_reminder', new_callable=AsyncMock) as mock_deliver,
        ):
            await task.run()

        mock_deliver.assert_called_once_with(reminder)
        mock_repo.mark_fired.assert_called_once()
        assert mock_repo.mark_fired.call_args[0][0] == reminder.reminder_id

    @pytest.mark.asyncio
    async def test_skips_future_reminders(self, guild):
        """run() does not fire reminders whose fire time is in the future."""
        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        reminder = _make_reminder(attu_year=99, attu_month=1, attu_day=1)
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[reminder])

        # fire time far in the future
        future_span = AttuYearSpan(start_time=9999999999, end_time=9999999999 + 1209600, duration=14)

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.get_year_span', new_callable=AsyncMock, return_value=future_span),
            patch('attubot.tasks.reminder._deliver_reminder', new_callable=AsyncMock) as mock_deliver,
        ):
            await task.run()

        mock_deliver.assert_not_called()
        mock_repo.mark_fired.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_fire_time_none(self, guild):
        """run() skips reminders whose fire time cannot be computed (paused guild, etc.)."""
        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        reminder = _make_reminder(attu_year=5)
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[reminder])

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.compute_fire_time', new_callable=AsyncMock, return_value=None),
            patch('attubot.tasks.reminder._deliver_reminder', new_callable=AsyncMock) as mock_deliver,
        ):
            await task.run()

        mock_deliver.assert_not_called()
        mock_repo.mark_fired.assert_not_called()


# --- ReminderTask.next_run ---


class TestReminderTaskNextRun:
    @pytest.mark.asyncio
    @freeze_time('2024-06-01 12:00:00')
    async def test_no_pending_reminders(self, guild):
        """returns ~30 minutes from now when there are no unfired reminders."""
        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[])

        with patch('attubot.tasks.reminder._reminder_repo', mock_repo):
            result = await task.next_run()

        assert result is not None
        from datetime import datetime

        expected = datetime(2024, 6, 1, 12, 30).astimezone()
        assert abs((result - expected).total_seconds()) < 5

    @pytest.mark.asyncio
    @freeze_time('2024-06-01 12:00:00')
    async def test_earliest_fire_time(self, guild):
        """returns the earliest fire time across all pending reminders."""
        from datetime import datetime

        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        r1 = _make_reminder(reminder_id='r1', attu_year=5, attu_month=6)
        r2 = _make_reminder(reminder_id='r2', attu_year=5, attu_month=3)

        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[r1, r2])

        # r1 fires later than r2
        fire_r1 = datetime(2024, 8, 1, 12, 0).astimezone()
        fire_r2 = datetime(2024, 7, 1, 12, 0).astimezone()

        async def mock_compute(reminder):
            if reminder.reminder_id == 'r1':
                return fire_r1
            return fire_r2

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.compute_fire_time', side_effect=mock_compute),
        ):
            result = await task.next_run()

        assert result is not None
        assert result == fire_r2

    @pytest.mark.asyncio
    @freeze_time('2024-06-01 12:00:00')
    async def test_overdue_returns_now(self, guild):
        """returns now when a reminder is already overdue."""
        from datetime import datetime

        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        reminder = _make_reminder(attu_year=1)
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[reminder])

        overdue_time = datetime(2024, 1, 1, 0, 0).astimezone()

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.compute_fire_time', new_callable=AsyncMock, return_value=overdue_time),
        ):
            result = await task.next_run()

        assert result is not None
        now = datetime(2024, 6, 1, 12, 0).astimezone()
        assert abs((result - now).total_seconds()) < 5

    @pytest.mark.asyncio
    @freeze_time('2024-06-01 12:00:00')
    async def test_all_paused_returns_30_minutes(self, guild):
        """returns ~30 minutes from now when all reminders belong to paused/unauthorized guilds."""
        from datetime import datetime

        from attubot.tasks.reminder import ReminderTask

        task = ReminderTask()

        reminder = _make_reminder(attu_year=5)
        mock_repo = AsyncMock()
        mock_repo.list_all_unfired = AsyncMock(return_value=[reminder])

        with (
            patch('attubot.tasks.reminder._reminder_repo', mock_repo),
            patch('attubot.tasks.reminder.compute_fire_time', new_callable=AsyncMock, return_value=None),
        ):
            result = await task.next_run()

        assert result is not None
        expected = datetime(2024, 6, 1, 12, 30).astimezone()
        assert abs((result - expected).total_seconds()) < 5
