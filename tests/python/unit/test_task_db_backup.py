# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_task_db_backup | tests for DatabaseBackupTask."""

import os
import time
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from freezegun import freeze_time

from nova_core.tasks.db_backup import DatabaseBackupTask, _cleanup_old_backups, _next_daily_at


# --- helpers ---


def _make_task() -> DatabaseBackupTask:
    """Return a fresh, unregistered task instance."""
    return DatabaseBackupTask()


def _make_config(path: str = '/backups', time: str = '03:00'):
    backup = MagicMock()
    backup.path = path
    backup.time = time

    database = MagicMock()
    database.url = 'mongodb://localhost:27017'
    database.name = 'testdb'

    cfg = MagicMock()
    cfg.backup = backup
    cfg.database = database
    cfg.wait_for_init = AsyncMock(return_value=True)
    return cfg


def _make_proc(returncode: int = 0) -> AsyncMock:
    mock = AsyncMock()
    mock.returncode = returncode
    mock.communicate = AsyncMock(return_value=(b'', b''))
    return mock


# --- _next_daily_at ---


class TestNextDailyAt:
    @freeze_time('2026-02-24 12:00:00', tz_offset=0)
    def test_returns_future_datetime(self):
        result = _next_daily_at('03:00')
        assert result > datetime.now().astimezone()

    @freeze_time('2026-02-24 12:00:00', tz_offset=0)
    def test_correct_time(self):
        result = _next_daily_at('17:30')
        assert result.hour == 17
        assert result.minute == 30

    @freeze_time('2026-02-24 03:00:30', tz_offset=0)  # just past 03:00
    def test_advances_by_one_day_when_already_passed(self):
        result = _next_daily_at('03:00')
        # 30s past target - should be tomorrow
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert delta > 60 * 60 * 23  # at least 23 hours away

    @freeze_time('2026-02-24 02:59:00', tz_offset=0)  # 1 min before
    def test_returns_today_when_upcoming(self):
        result = _next_daily_at('03:00')
        # 1 minute away - should NOT jump a day
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert 0 < delta < 120


# --- on_start ---


class TestOnStart:
    async def test_disabled_when_path_empty(self):
        task = _make_task()
        cfg = _make_config(path='')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('shutil.which', return_value='/usr/bin/mongodump'):
            await task.on_start()

        assert task._enabled is False

    async def test_disabled_when_mongodump_missing(self):
        task = _make_task()
        cfg = _make_config(path='/backups')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('shutil.which', return_value=None):
            await task.on_start()

        assert task._enabled is False

    async def test_enabled_when_configured(self):
        task = _make_task()
        cfg = _make_config(path='/backups')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('shutil.which', return_value='/usr/bin/mongodump'):
            await task.on_start()

        assert task._enabled is True


# --- next_run ---


class TestNextRun:
    async def test_returns_far_future_when_disabled(self):
        task = _make_task()
        task._enabled = False
        result = await task.next_run()
        assert result is not None
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert delta > 60 * 60 * 24 * 300  # at least 300 days

    @freeze_time('2026-02-24 12:00:00', tz_offset=0)
    async def test_returns_next_scheduled_time_when_enabled(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(time='03:00')
        with patch('nova_core.tasks.db_backup.config', cfg):
            result = await task.next_run()

        assert result is not None
        # frozen at 12:00, target is 03:00 - already past, so should be tomorrow (15h away)
        delta = (result - datetime.now().astimezone()).total_seconds()
        assert delta > 60 * 60 * 14  # tomorrow's 03:00 is ~15h from noon


# --- run ---


class TestRun:
    async def test_no_op_when_disabled(self):
        task = _make_task()
        task._enabled = False

        with patch('asyncio.create_subprocess_exec') as mock_exec:
            await task.run()
            mock_exec.assert_not_called()

    async def test_calls_mongodump_then_tar(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups', time='03:00')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=[_make_proc(), _make_proc()]) as mock_exec, patch('nova_core.tasks.db_backup._cleanup_old_backups'):
            await task.run()

        assert mock_exec.call_count == 2
        first_call = mock_exec.call_args_list[0][0]
        second_call = mock_exec.call_args_list[1][0]
        assert first_call[0] == 'mongodump'
        assert second_call[0] == 'tar'

    async def test_mongodump_called_with_correct_args(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups', time='03:00')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=[_make_proc(), _make_proc()]) as mock_exec, patch('nova_core.tasks.db_backup._cleanup_old_backups'):
            await task.run()

        dump_args = mock_exec.call_args_list[0][0]
        assert any('mongodb://localhost:27017' in a for a in dump_args)
        assert any('testdb' in a for a in dump_args)

    async def test_tar_creates_bz2_archive(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=[_make_proc(), _make_proc()]) as mock_exec, patch('nova_core.tasks.db_backup._cleanup_old_backups'):
            await task.run()

        tar_args = mock_exec.call_args_list[1][0]
        assert tar_args[0] == 'tar'
        assert '-cjf' in tar_args
        assert any(a.endswith('.tar.bz2') for a in tar_args)

    async def test_tar_not_called_on_mongodump_failure(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=[_make_proc(returncode=1)]) as mock_exec, patch('nova_core.tasks.db_backup._cleanup_old_backups') as mock_cleanup:
            await task.run()

        assert mock_exec.call_count == 1
        mock_cleanup.assert_not_called()

    async def test_cleanup_not_called_on_tar_failure(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=[_make_proc(), _make_proc(returncode=1)]), patch('nova_core.tasks.db_backup._cleanup_old_backups') as mock_cleanup:
            await task.run()

        mock_cleanup.assert_not_called()

    async def test_logs_error_on_mongodump_failure(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        proc = _make_proc(returncode=1)
        proc.communicate = AsyncMock(return_value=(b'', b'connection refused'))

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', return_value=proc), patch('nova_core.tasks.db_backup.logger') as mock_logger:
            await task.run()

        mock_logger.error.assert_called_once()
        assert 'connection refused' in mock_logger.error.call_args[0][0]

    @freeze_time('2026-02-22 03:00:00', tz_offset=0)
    async def test_archive_filename_uses_timestamp(self):
        task = _make_task()
        task._enabled = True

        cfg = _make_config(path='/backups')

        captured = []

        async def fake_exec(*args, **kwargs):
            captured.extend(args)
            return _make_proc()

        with patch('nova_core.tasks.db_backup.config', cfg), patch('asyncio.create_subprocess_exec', side_effect=fake_exec), patch('nova_core.tasks.db_backup._cleanup_old_backups'):
            await task.run()

        # archive path is the first positional arg after '-cjf' in the tar call
        tar_args = [a for a in captured if a == 'tar' or (isinstance(a, str) and '.tar.bz2' in a)]
        assert any('2026-02-22' in a for a in tar_args)


# --- _cleanup_old_backups ---


class TestCleanupOldBackups:
    def test_removes_files_older_than_retention(self, tmp_path):
        old_file = tmp_path / '2025-01-01_030000.tar.bz2'
        old_file.touch()
        # set mtime to 200 days ago
        old_mtime = time.time() - (200 * 86400)
        os.utime(old_file, (old_mtime, old_mtime))

        _cleanup_old_backups(str(tmp_path))

        assert not old_file.exists()

    def test_keeps_recent_files(self, tmp_path):
        recent_file = tmp_path / '2026-03-10_030000.tar.bz2'
        recent_file.touch()
        # mtime defaults to now - well within retention

        _cleanup_old_backups(str(tmp_path))

        assert recent_file.exists()

    def test_ignores_non_bz2_files(self, tmp_path):
        old_dir = tmp_path / '2025-01-01_030000'
        old_dir.mkdir()
        old_txt = tmp_path / 'notes.txt'
        old_txt.touch()
        old_mtime = time.time() - (200 * 86400)
        os.utime(old_txt, (old_mtime, old_mtime))

        _cleanup_old_backups(str(tmp_path))

        # directory and txt not removed
        assert old_dir.exists()
        assert old_txt.exists()

    def test_removes_only_old_files_when_mixed(self, tmp_path):
        old_file = tmp_path / '2025-01-01_030000.tar.bz2'
        old_file.touch()
        old_mtime = time.time() - (200 * 86400)
        os.utime(old_file, (old_mtime, old_mtime))

        recent_file = tmp_path / '2026-03-10_030000.tar.bz2'
        recent_file.touch()

        _cleanup_old_backups(str(tmp_path))

        assert not old_file.exists()
        assert recent_file.exists()
