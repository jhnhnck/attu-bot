# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_signals | tests for cross-process reload signaling."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nova_core.database.models import ReloadSignalDocument


test_guild = 1234567890
test_guild_2 = 9876543210


# --- ReloadSignalDocument ---


class TestReloadSignalDocument:
    def test_make_guild(self):
        doc = ReloadSignalDocument.make('guild', test_guild)
        assert doc.signal_type == 'guild'
        assert doc.guild_id == test_guild
        assert doc.timestamp > 0

    def test_make_theme(self):
        doc = ReloadSignalDocument.make('theme')
        assert doc.signal_type == 'theme'
        assert doc.guild_id is None

    def test_make_system(self):
        doc = ReloadSignalDocument.make('system')
        assert doc.signal_type == 'system'
        assert doc.guild_id is None

    def test_timestamp_is_current(self):
        before = int(time.time())
        doc = ReloadSignalDocument.make('theme')
        after = int(time.time())
        assert before <= doc.timestamp <= after

    def test_extra_fields_ignored(self):
        # extra='ignore' should tolerate unknown fields
        doc = ReloadSignalDocument(signal_type='theme', guild_id=None, timestamp=0, unknown_field='x')  # pyright: ignore[reportCallIssue]
        assert doc.signal_type == 'theme'


# --- ReloadSignalRepository ---


@pytest.fixture
def signal_repo():
    """Create a ReloadSignalRepository with a mock async MongoDB collection."""
    from nova_core.database.repositories import ReloadSignalRepository

    mock_db = MagicMock()
    repo = ReloadSignalRepository(mock_db)
    return repo


class TestReloadSignalRepository:
    async def test_init_indexes(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].create_index = AsyncMock()
        await signal_repo.init_indexes()
        signal_repo.db[signal_repo.COLLECTION].create_index.assert_called_once()

    async def test_send_upserts_guild(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].update_one = AsyncMock()
        await signal_repo.send('guild', test_guild)
        signal_repo.db[signal_repo.COLLECTION].update_one.assert_called_once()
        call_args = signal_repo.db[signal_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'target': 'bot', 'signal_type': 'guild', 'guild_id': test_guild}
        assert call_args[1]['upsert'] is True

    async def test_send_upserts_theme(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].update_one = AsyncMock()
        await signal_repo.send('theme')
        call_args = signal_repo.db[signal_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'target': 'bot', 'signal_type': 'theme', 'guild_id': None}
        assert call_args[1]['upsert'] is True

    async def test_send_sets_timestamp(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].update_one = AsyncMock()
        before = int(time.time())
        await signal_repo.send('system')
        after = int(time.time())
        call_args = signal_repo.db[signal_repo.COLLECTION].update_one.call_args
        doc = call_args[0][1]['$set']
        assert before <= doc['timestamp'] <= after

    async def test_consume_all_empty(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete = AsyncMock(return_value=None)
        result = await signal_repo.consume_all()
        assert result == []
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete.assert_called_once_with({'target': 'bot'})

    async def test_consume_all_returns_signals(self, signal_repo):
        fake_id = 'fake_oid_1'
        raw_doc = {'_id': fake_id, 'signal_type': 'guild', 'guild_id': test_guild, 'timestamp': 1000}
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete = AsyncMock(side_effect=[raw_doc, None])
        result = await signal_repo.consume_all()
        assert len(result) == 1
        assert result[0].signal_type == 'guild'
        assert result[0].guild_id == test_guild

    async def test_consume_all_deletes_processed(self, signal_repo):
        fake_id = 'fake_oid_1'
        raw_doc = {'_id': fake_id, 'signal_type': 'theme', 'guild_id': None, 'timestamp': 1000}
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete = AsyncMock(side_effect=[raw_doc, None])
        await signal_repo.consume_all()
        # find_one_and_delete atomically deletes each doc; verify it was called for the doc
        assert signal_repo.db[signal_repo.COLLECTION].find_one_and_delete.call_count == 2

    async def test_consume_all_multiple_signals(self, signal_repo):
        raw_docs = [
            {'_id': 'id1', 'signal_type': 'guild', 'guild_id': test_guild, 'timestamp': 1000},
            {'_id': 'id2', 'signal_type': 'theme', 'guild_id': None, 'timestamp': 1001},
            {'_id': 'id3', 'signal_type': 'system', 'guild_id': None, 'timestamp': 1002},
        ]
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete = AsyncMock(side_effect=[*raw_docs, None])
        result = await signal_repo.consume_all()
        assert len(result) == 3
        types = {r.signal_type for r in result}
        assert types == {'guild', 'theme', 'system'}
        assert signal_repo.db[signal_repo.COLLECTION].find_one_and_delete.call_count == 4

    async def test_collection_name(self, signal_repo):
        assert signal_repo.COLLECTION == 'reload_signals'


# --- ReloadWatcher cog ---


@pytest.fixture
def mock_signal_repo():
    """patch reload_watcher._get_repo to return an AsyncMock repository."""
    repo = AsyncMock()
    with patch('nova_core.tasks.reload_watcher._get_repo', return_value=repo):
        yield repo


@pytest.fixture
def mock_cfg():
    """Patch nova_core.tasks.reload_watcher.config with async load methods."""
    cfg = MagicMock()
    cfg.load_guild = AsyncMock()
    cfg.load_theme = AsyncMock()
    cfg.load_globals = AsyncMock()
    cfg.wait_for_load = AsyncMock()
    with patch('nova_core.tasks.reload_watcher.config', cfg):
        yield cfg


def make_watcher(target: str = 'bot'):
    """Instantiate ReloadWatcherTask without starting the task loop."""
    from nova_core.tasks.reload_watcher import ReloadWatcherTask

    return ReloadWatcherTask(target=target)


class TestReloadWatcher:
    async def test_no_signals_is_noop(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(return_value=[])
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_not_called()
        mock_cfg.load_theme.assert_not_called()
        mock_cfg.load_globals.assert_not_called()

    async def test_guild_signal_reloads_guild(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild, timestamp=1000),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_called_once_with(test_guild)

    async def test_theme_signal_reloads_theme(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='theme', guild_id=None, timestamp=1000),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_theme.assert_called_once()
        mock_cfg.load_guild.assert_not_called()

    async def test_system_signal_reloads_globals(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='system', guild_id=None, timestamp=1000),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_globals.assert_called_once()
        mock_cfg.load_guild.assert_not_called()

    async def test_guild_signal_without_guild_id_is_skipped(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=None, timestamp=1000),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_not_called()

    async def test_multiple_guild_signals(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild, timestamp=1000),
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild_2, timestamp=1001),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        assert mock_cfg.load_guild.call_count == 2
        mock_cfg.load_guild.assert_any_call(test_guild)
        mock_cfg.load_guild.assert_any_call(test_guild_2)

    async def test_mixed_signal_types(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild, timestamp=1000),
                ReloadSignalDocument(signal_type='theme', guild_id=None, timestamp=1001),
                ReloadSignalDocument(signal_type='system', guild_id=None, timestamp=1002),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_called_once_with(test_guild)
        mock_cfg.load_theme.assert_called_once()
        mock_cfg.load_globals.assert_called_once()

    async def test_error_in_one_signal_continues_others(self, mock_signal_repo, mock_cfg):
        # guild reload raises, but theme should still be processed
        mock_cfg.load_guild = AsyncMock(side_effect=Exception('db fail'))
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild, timestamp=1000),
                ReloadSignalDocument(signal_type='theme', guild_id=None, timestamp=1001),
            ],
        )
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_theme.assert_called_once()

    async def test_repo_error_is_caught(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(side_effect=Exception('mongo connection lost'))
        from nova_core.tasks.reload_watcher import ReloadWatcherTask

        # should not raise - error is logged and function returns
        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_not_called()
