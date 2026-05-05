"""
AttuBot - Tests for cross-process reload signaling
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.database.models import ReloadSignalDocument


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

    def test_make_chat(self):
        doc = ReloadSignalDocument.make('chat')
        assert doc.signal_type == 'chat'
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
    from attubot.database.repositories import ReloadSignalRepository

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

    async def test_send_to_ingestor_target(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].update_one = AsyncMock()
        await signal_repo.send('chat', target='ingestor')
        call_args = signal_repo.db[signal_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'target': 'ingestor', 'signal_type': 'chat', 'guild_id': None}
        assert call_args[0][1]['$set']['target'] == 'ingestor'

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

    async def test_consume_all_filters_by_target(self, signal_repo):
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete = AsyncMock(return_value=None)
        await signal_repo.consume_all(target='ingestor')
        signal_repo.db[signal_repo.COLLECTION].find_one_and_delete.assert_called_once_with({'target': 'ingestor'})

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


# --- send_signal() helper ---


@pytest.fixture
def mock_signal_repo():
    """Patch attubot.database.signals._get_repo and reload_watcher._get_repo to return an AsyncMock repository."""
    repo = AsyncMock()
    with patch('attubot.signals._get_repo', return_value=repo), patch('attubot.tasks.reload_watcher._get_repo', return_value=repo):
        yield repo


class TestSendSignalHelper:
    async def test_sends_guild_signal(self, mock_signal_repo):
        from attubot.signals import send_signal

        await send_signal('guild', test_guild)
        mock_signal_repo.send.assert_called_once_with('guild', test_guild, target='bot')

    async def test_sends_theme_signal(self, mock_signal_repo):
        from attubot.signals import send_signal

        await send_signal('theme')
        mock_signal_repo.send.assert_called_once_with('theme', None, target='bot')

    async def test_sends_system_signal(self, mock_signal_repo):
        from attubot.signals import send_signal

        await send_signal('system')
        mock_signal_repo.send.assert_called_once_with('system', None, target='bot')

    async def test_chat_signal_fans_out_to_bot_and_ingestor(self, mock_signal_repo):
        from attubot.signals import send_signal

        await send_signal('chat')
        targets = {call.kwargs.get('target') for call in mock_signal_repo.send.call_args_list}
        assert targets == {'bot', 'ingestor'}
        assert mock_signal_repo.send.call_count == 2

    async def test_swallows_exception(self, mock_signal_repo):
        from attubot.signals import send_signal

        mock_signal_repo.send = AsyncMock(side_effect=Exception('db gone'))
        # should not raise - errors are logged but never re-raised
        await send_signal('guild', test_guild)

    async def test_swallows_connection_error(self, mock_signal_repo):
        from attubot.signals import send_signal

        mock_signal_repo.send = AsyncMock(side_effect=ConnectionError('mongo down'))
        await send_signal('theme')


# --- ReloadWatcher cog ---


@pytest.fixture
def mock_cfg():
    """Patch attubot.tasks.reload_watcher.config with async load methods."""
    cfg = MagicMock()
    cfg.load_guild = AsyncMock()
    cfg.load_theme = AsyncMock()
    cfg.load_globals = AsyncMock()
    cfg.load_chat_runtime = AsyncMock()
    cfg.wait_for_load = AsyncMock()
    with patch('attubot.tasks.reload_watcher.config', cfg):
        yield cfg


def make_watcher(target: str = 'bot'):
    """Instantiate ReloadWatcherTask without starting the task loop."""
    from attubot.tasks.reload_watcher import ReloadWatcherTask

    return ReloadWatcherTask(target=target)


class TestReloadWatcher:
    async def test_no_signals_is_noop(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(return_value=[])
        from attubot.tasks.reload_watcher import ReloadWatcherTask

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
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_called_once_with(test_guild)

    async def test_theme_signal_reloads_theme(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='theme', guild_id=None, timestamp=1000),
            ],
        )
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_theme.assert_called_once()
        mock_cfg.load_guild.assert_not_called()

    async def test_system_signal_reloads_globals(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='system', guild_id=None, timestamp=1000),
            ],
        )
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_globals.assert_called_once()
        mock_cfg.load_guild.assert_not_called()

    async def test_guild_signal_without_guild_id_is_skipped(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=None, timestamp=1000),
            ],
        )
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_not_called()

    async def test_multiple_guild_signals(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild, timestamp=1000),
                ReloadSignalDocument(signal_type='guild', guild_id=test_guild_2, timestamp=1001),
            ],
        )
        from attubot.tasks.reload_watcher import ReloadWatcherTask

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
        from attubot.tasks.reload_watcher import ReloadWatcherTask

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
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_theme.assert_called_once()

    async def test_chat_signal_reloads_chat_runtime(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(
            return_value=[
                ReloadSignalDocument(signal_type='chat', guild_id=None, timestamp=1000),
            ],
        )
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_chat_runtime.assert_called_once()
        mock_cfg.load_guild.assert_not_called()

    async def test_repo_error_is_caught(self, mock_signal_repo, mock_cfg):
        mock_signal_repo.consume_all = AsyncMock(side_effect=Exception('mongo connection lost'))
        from attubot.tasks.reload_watcher import ReloadWatcherTask

        # should not raise - error is logged and function returns
        await ReloadWatcherTask.run(make_watcher())
        mock_cfg.load_guild.assert_not_called()


# --- Web route signal emission ---

from attubot.config import BotTheme, GuildChannels, GuildConfig, GuildEpoch, GuildRoles, GuildUsers


@pytest_asyncio.fixture(scope='function')
async def web_app_with_signals():
    """Web app fixture that also patches send_signal for assertion."""
    from attubot.web import app as web_app_module
    from attubot.web.app import create_app

    guild = GuildConfig(
        id=test_guild,
        channels=GuildChannels(activity=111111, announcements=222222),
        epoch=GuildEpoch(time=1704067200, year=5, length=14, paused=False, rollover_minutes=1020),
        roles=GuildRoles(announcements=999999),
        users=GuildUsers(markers=[111]),
    )
    theme = BotTheme(rotation=0.0, max_rate=0.5, bot_color='#ff0000', guild_color='#ffffff')

    web_app_module.config.authorized_guilds = {test_guild}
    web_app_module.config.valid_guilds = [test_guild]
    web_app_module.config.primary_guild = test_guild
    web_app_module.config.guilds = {test_guild: guild}
    web_app_module.config.theme = theme
    web_app_module.config.load_guild = AsyncMock(return_value=True)
    web_app_module.config.load_globals = AsyncMock()
    web_app_module.config.config_repo = MagicMock()
    web_app_module.config.config_repo.update_system_field = AsyncMock()
    web_app_module.config.error_log = (test_guild, 123456)
    web_app_module.config.error_hook = 'https://discord.com/api/webhooks/123/abc'
    web_app_module.config.config_version = '2.2.0'

    from attubot.config import PathsConfig, WebConfig

    web_app_module.config.web = WebConfig(secret_key='test-secret-key')
    web_app_module.config.paths = PathsConfig(assets='./assets')
    web_app_module.config._get_event('init').set()
    web_app_module.audit_logger = None

    with patch.object(GuildConfig, 'save', new=AsyncMock()), patch.object(BotTheme, 'save', new=AsyncMock()):
        app = create_app()
        app.config['TESTING'] = True
        yield app


@pytest_asyncio.fixture(scope='function')
async def signal_client(web_app_with_signals):
    return web_app_with_signals.test_client()


class TestWebRoutesEmitSignals:
    @pytest.mark.asyncio
    async def test_guild_save_emits_guild_signal(self, signal_client):
        payload = {
            'channels': {'activity': 999999},
            'epoch': {'year': 3},
        }
        with patch('attubot.web.routes.send_signal', new=AsyncMock()) as mock_send:
            response = await signal_client.post(f'/api/guilds/{test_guild}', json=payload)
            assert response.status_code == 200
            mock_send.assert_called_once_with('guild', test_guild)

    @pytest.mark.asyncio
    async def test_theme_save_emits_theme_signal(self, signal_client):
        payload = {
            'rotation': 45.0,
            'bot_color': '#0000ff',
        }
        with patch('attubot.web.routes.send_signal', new=AsyncMock()) as mock_send:
            response = await signal_client.post('/api/theme', json=payload)
            assert response.status_code == 200
            mock_send.assert_called_once_with('theme')

    @pytest.mark.asyncio
    async def test_system_save_emits_system_signal(self, signal_client):
        payload = {
            'primary_guild': test_guild,
            'error_log_guild': test_guild,
            'error_log_channel': 123456,
            'error_hook': 'https://discord.com/api/webhooks/123/abc',
        }
        with patch('attubot.web.routes.send_signal', new=AsyncMock()) as mock_send:
            response = await signal_client.post('/api/system', json=payload)
            assert response.status_code == 200
            mock_send.assert_called_once_with('system')

    @pytest.mark.asyncio
    async def test_guild_save_validation_error_does_not_emit(self, signal_client):
        # invalid payload - should 400 and never reach send_signal
        payload = {
            'epoch': {'year': -999, 'length': -1, 'time': 0, 'paused': False, 'rollover_minutes': 1020},
        }
        with patch('attubot.web.routes.send_signal', new=AsyncMock()) as mock_send:
            response = await signal_client.post(f'/api/guilds/{test_guild}', json=payload)
            assert response.status_code == 400
            mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_guild_save_db_error_does_not_emit(self, signal_client):
        from attubot.web.app import config as web_config

        web_config.guilds[test_guild].save.side_effect = Exception('db gone')
        payload = {'channels': {'activity': 1}}
        with patch('attubot.web.routes.send_signal', new=AsyncMock()) as mock_send:
            response = await signal_client.post(f'/api/guilds/{test_guild}', json=payload)
            assert response.status_code == 500
            mock_send.assert_not_called()
        web_config.guilds[test_guild].save.side_effect = None
