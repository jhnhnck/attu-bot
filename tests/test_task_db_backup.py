"""
AttuBot - Tests for DatabaseBackupTask
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun import freeze_time

from attubot.tasks.db_backup import DatabaseBackupTask, _next_weekday_at

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_task() -> DatabaseBackupTask:
    """Return a fresh, unregistered task instance."""
    return DatabaseBackupTask()


def _make_config(path: str = '/backups', day: str = 'sunday', time: str = '03:00'):
    backup = MagicMock()
    backup.path = path
    backup.day = day
    backup.time = time

    database = MagicMock()
    database.url = 'mongodb://localhost:27017'
    database.name = 'testdb'

    cfg = MagicMock()
    cfg.backup = backup
    cfg.database = database
    cfg.wait_for_init = AsyncMock(return_value=True)
    return cfg


# ---------------------------------------------------------------------------
# _next_weekday_at
# ---------------------------------------------------------------------------


class TestNextWeekdayAt:
    # freeze to a tuesday at 12:00 UTC
    @freeze_time('2026-02-24 12:00:00', tz_offset=0)
    def test_returns_future_datetime(self):
        result = _next_weekday_at('sunday', '03:00')
        assert result > datetime.now().astimezone()

    @freeze_time('2026-02-24 12:00:00', tz_offset=0)  # tuesday
    def test_correct_weekday(self):
        result = _next_weekday_at('sunday', '03:00')
        # next sunday from tuesday 2026-02-24 is 2026-03-01
        assert result.isoweekday() == 7  # sunday

    @freeze_time('2026-02-24 12:00:00', tz_offset=0)  # tuesday
    def test_correct_time(self):
        result = _next_weekday_at('friday', '17:30')
        assert result.hour == 17
        assert result.minute == 30

    @freeze_time('2026-02-22 03:00:30', tz_offset=0)  # sunday, just past 03:00
    def test_advances_by_one_week_when_already_passed(self):
        # frozen at sunday 03:00:30 — the target moment is 30s in the past; expect next sunday
        result = _next_weekday_at('sunday', '03:00')
        assert result.isoweekday() == 7
        # should be ~7 days from now, not ~0
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert delta > 60 * 60 * 24 * 6  # at least 6 days away

    @freeze_time('2026-02-22 02:59:00', tz_offset=0)  # sunday, 1 min before
    def test_returns_current_week_when_upcoming(self):
        result = _next_weekday_at('sunday', '03:00')
        # 1 minute away - should NOT jump a week
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert 0 < delta < 120


# ---------------------------------------------------------------------------
# on_start
# ---------------------------------------------------------------------------


class TestOnStart:
    async def test_disabled_when_path_empty(self):
        task = _make_task()
        cfg = _make_config(path='')

        with patch('attubot.tasks.db_backup.config', cfg), patch('shutil.which', return_value='/usr/bin/mongodump'):
            await task.on_start()

        assert task._enabled is False

    async def test_disabled_when_mongodump_missing(self):
        task = _make_task()
        cfg = _make_config(path='/backups')

        with patch('attubot.tasks.db_backup.config', cfg), patch('shutil.which', return_value=None):
            await task.on_start()

        assert task._enabled is False

    async def test_enabled_when_configured(self):
        task = _make_task()
        cfg = _make_config(path='/backups')

        with patch('attubot.tasks.db_backup.config', cfg), patch('shutil.which', return_value='/usr/bin/mongodump'):
            await task.on_start()

        assert task._enabled is True


# ---------------------------------------------------------------------------
# next_run
# ---------------------------------------------------------------------------


class TestNextRun:
    async def test_returns_far_future_when_disabled(self):
        task = _make_task()
        task._enabled = False
        result = await task.next_run()
        assert result is not None
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert delta > 60 * 60 * 24 * 300  # at least 300 days

    @freeze_time('2026-02-24 12:00:00', tz_offset=0)  # tuesday
    async def test_returns_next_scheduled_time_when_enabled(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(day='sunday', time='03:00')
        with patch('attubot.tasks.db_backup.config', cfg):
            result = await task.next_run()

        assert result is not None
        assert result.isoweekday() == 7  # sunday


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


class TestRun:
    async def test_no_op_when_disabled(self):
        task = _make_task()
        task._enabled = False

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            await task.run()
            mock_exec.assert_not_called()

    async def test_calls_mongodump_with_correct_args(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups', day='sunday', time='03:00')

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'', b''))

        with patch('attubot.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', return_value=mock_proc) as mock_exec:
            await task.run()

        mock_exec.assert_called_once()
        call_args = mock_exec.call_args[0]
        assert call_args[0] == 'mongodump'
        assert any('mongodb://localhost:27017' in a for a in call_args)
        assert any('testdb' in a for a in call_args)
        assert any('/backups/' in a for a in call_args)

    async def test_logs_error_on_nonzero_exit(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b'', b'connection refused'))

        with patch('attubot.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', return_value=mock_proc), patch('attubot.tasks.db_backup.logger') as mock_logger:
            await task.run()

        mock_logger.error.assert_called_once()
        err_msg = mock_logger.error.call_args[0][0]
        assert 'connection refused' in err_msg

    @freeze_time('2026-02-22 03:00:00', tz_offset=0)
    async def test_output_dir_uses_timestamp(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b'', b''))

        captured_args = []

        async def fake_exec(*args, **kwargs):
            captured_args.extend(args)
            return mock_proc

        with patch('attubot.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=fake_exec):
            await task.run()

        out_arg = next(a for a in captured_args if '/backups/' in a)
        assert '2026-02-22' in out_arg
