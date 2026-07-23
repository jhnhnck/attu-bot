"""
AttuBot - ReloadWatcherTask Component Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests real signal consumption from MongoDB and resulting config state mutations.
Uses a real ConfigRepository + ReloadSignalRepository on isolated component_db collections.
"""

from unittest.mock import patch

import pytest

from nova_core.client.core import config
from nova_core.database.repositories import ConfigRepository, ReloadSignalRepository


pytestmark = pytest.mark.component

test_guild = 1234567890


def _make_task():
    from nova_core.tasks.reload_watcher import ReloadWatcherTask

    return ReloadWatcherTask()


class TestReloadWatcherSignalConsumption:
    async def test_guild_signal_reloads_guild_epoch_from_db(self, component_db, make_guild):
        """a guild signal causes the in-memory config to reflect the updated epoch from DB"""
        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        guild_cfg = make_guild(guild_id=test_guild)
        saved_config_repo = config.config_repo
        config.config_repo = config_repo

        try:
            # save year=5 to DB, then reset in-memory to year=1
            guild_cfg.epoch.year = 5
            await config_repo.save_guild(guild_cfg)
            config.guilds[test_guild].epoch.year = 1

            await signal_repo.send('guild', test_guild)

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            assert config.guilds[test_guild].epoch.year == 5
        finally:
            config.config_repo = saved_config_repo

    async def test_signals_consumed_from_db_after_run(self, component_db, make_guild):
        """signals are deleted from the collection after run() processes them"""
        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        make_guild(guild_id=test_guild)
        saved_config_repo = config.config_repo
        config.config_repo = config_repo

        try:
            await config_repo.save_guild(config.guilds[test_guild])
            await signal_repo.send('guild', test_guild)

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            remaining = await signal_repo.consume_all()
            assert remaining == []
        finally:
            config.config_repo = saved_config_repo

    async def test_theme_signal_reloads_theme_from_db(self, component_db):
        """a theme signal causes config.theme to reflect the saved theme doc"""
        from nova_core.config import BotTheme

        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        saved_config_repo = config.config_repo
        saved_theme = config.theme
        config.config_repo = config_repo

        try:
            theme = BotTheme(rotation=45.0, max_rate=0.8, bot_color='#0000ff', guild_color='#ffffff')
            await config_repo.save_theme(theme)
            config.theme = None

            await signal_repo.send('theme')

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            assert config.theme is not None
            assert config.theme.bot_color == '#0000ff'
            assert config.theme.rotation == 45.0
        finally:
            config.config_repo = saved_config_repo
            config.theme = saved_theme

    async def test_system_signal_reloads_error_hook_from_db(self, component_db):
        """a system signal causes config.error_hook to reflect the saved system doc"""
        from nova_core.database.models import SystemConfigDocument

        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        saved_config_repo = config.config_repo
        saved_error_hook = config.error_hook
        config.config_repo = config_repo

        try:
            system = SystemConfigDocument(
                version='2.5.1',
                error_log=[test_guild, 0],
                error_hook='https://discord.com/api/webhooks/test/new-hook',
                primary_guild=test_guild,
            )
            await config_repo.save_system(system)
            config.error_hook = 'https://old-hook.example.com'

            await signal_repo.send('system')

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            assert config.error_hook == 'https://discord.com/api/webhooks/test/new-hook'
        finally:
            config.config_repo = saved_config_repo
            config.error_hook = saved_error_hook

    async def test_multiple_signals_all_processed_in_one_run(self, component_db, make_guild):
        """guild, theme, and system signals in the same run are all applied"""
        from nova_core.config import BotTheme
        from nova_core.database.models import SystemConfigDocument

        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        make_guild(guild_id=test_guild)
        saved_config_repo = config.config_repo
        saved_theme = config.theme
        saved_error_hook = config.error_hook
        config.config_repo = config_repo

        try:
            config.guilds[test_guild].epoch.year = 7
            await config_repo.save_guild(config.guilds[test_guild])
            config.guilds[test_guild].epoch.year = 1

            await config_repo.save_theme(BotTheme(rotation=90.0, max_rate=0.5, bot_color='#00ff00', guild_color='#ffffff'))
            config.theme = None

            system = SystemConfigDocument(version='2.5.1', error_log=[test_guild, 0], error_hook='https://new-hook', primary_guild=test_guild)
            await config_repo.save_system(system)
            config.error_hook = 'old'

            await signal_repo.send('guild', test_guild)
            await signal_repo.send('theme')
            await signal_repo.send('system')

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            assert config.guilds[test_guild].epoch.year == 7
            assert config.theme is not None
            assert config.theme.bot_color == '#00ff00'
            assert config.error_hook == 'https://new-hook'
        finally:
            config.config_repo = saved_config_repo
            config.theme = saved_theme
            config.error_hook = saved_error_hook

    async def test_empty_signal_list_is_noop(self, component_db):
        """with no signals in the DB, run() returns without touching config"""
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        original_guilds = dict(config.guilds)

        with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
            await _make_task().run()

        assert dict(config.guilds) == original_guilds

    async def test_duplicate_signals_coalesce_to_one_effect(self, component_db, make_guild):
        """sending the same (type, guild_id) twice upserts to one signal - only one reload happens"""
        config_repo = ConfigRepository(component_db)
        await config_repo.init_indexes()
        signal_repo = ReloadSignalRepository(component_db)
        await signal_repo.init_indexes()

        make_guild(guild_id=test_guild)
        saved_config_repo = config.config_repo
        config.config_repo = config_repo

        try:
            config.guilds[test_guild].epoch.year = 3
            await config_repo.save_guild(config.guilds[test_guild])
            config.guilds[test_guild].epoch.year = 1

            # send the same guild signal twice - they coalesce in the DB
            await signal_repo.send('guild', test_guild)
            await signal_repo.send('guild', test_guild)

            with patch('nova_core.tasks.reload_watcher._repo', signal_repo):
                await _make_task().run()

            # effect should still apply
            assert config.guilds[test_guild].epoch.year == 3
            # and signals are gone
            assert await signal_repo.consume_all() == []
        finally:
            config.config_repo = saved_config_repo
