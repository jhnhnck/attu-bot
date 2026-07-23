"""
AttuBot - start_bot_loop() Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Fast, offline tests for the pre-network startup pipeline in nova_core/client/__init__.py.
No real Discord connection, no MongoDB, no filesystem access needed.
"""

import secrets
from unittest.mock import call, patch

import pytest

import nova_core.client as nova_core


# --- helpers ---


def _patch_all_startup(
    *,
    which_side_effect=None,
    which_return='/usr/bin/cmd',
    load_ext_side_effect=None,
):
    """context manager stack that patches all startup operations.
    returns the combined context as a list of patches in the order:
      [mock_on_init, mock_which, mock_load_handlers, mock_add_cmd, mock_load_ext, mock_run]
    """
    return (
        patch.object(nova_core.config, 'on_init'),
        patch('shutil.which', return_value=which_return, side_effect=which_side_effect),
        patch('nova_core.client._load_event_handlers'),
        patch.object(nova_core.bot, 'add_application_command'),
        patch.object(nova_core.bot, 'load_extension', side_effect=load_ext_side_effect),
        patch.object(nova_core.bot, 'run'),
    )


# ============================================================
# start_bot_loop() - full pipeline
# ============================================================


class TestSetupDiscordLogging:
    """unit: _setup_discord_logging() bridges pycord rate-limit logs to the project logger"""

    def test_attaches_handler_to_discord_http_logger(self):
        """a PycordBridgeHandler is added to the discord.http stdlib logger"""
        import logging as _logging

        from nova_core.client import PycordBridgeHandler

        discord_http_logger = _logging.getLogger('discord.http')
        initial_count = len(discord_http_logger.handlers)

        nova_core._setup_discord_logging()

        new_handlers = discord_http_logger.handlers[initial_count:]
        assert any(isinstance(h, PycordBridgeHandler) for h in new_handlers)

        # cleanup: remove the handler we just added
        for h in new_handlers:
            if isinstance(h, PycordBridgeHandler):
                discord_http_logger.removeHandler(h)

    def test_sets_discord_http_logger_to_debug(self):
        """discord.http logger level is set to DEBUG"""
        import logging as _logging

        discord_http_logger = _logging.getLogger('discord.http')
        original_level = discord_http_logger.level

        nova_core._setup_discord_logging()

        assert discord_http_logger.level == _logging.DEBUG

        # cleanup
        discord_http_logger.setLevel(original_level)
        from nova_core.client import PycordBridgeHandler

        for h in list(discord_http_logger.handlers):
            if isinstance(h, PycordBridgeHandler):
                discord_http_logger.removeHandler(h)

    def test_root_logger_has_dual_stream_handlers(self):
        """structlog config installs one stdout (< WARNING) and one stderr (>= WARNING) handler on root.

        compensates for PycordBridgeHandler no longer routing records itself; the real stdout/stderr
        split now lives on the root logger via attu_logging.configure().
        """
        import logging as _logging
        import sys

        import attu_logging  # noqa: F401 - imported for side effect; configure() called in conftest

        root = _logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_attu_owned', False)]

        assert len(owned) >= 2, f'expected at least 2 attu_logging-owned handlers, got {len(owned)}'

        streams = {h.stream for h in owned if isinstance(h, _logging.StreamHandler)}
        assert sys.stdout in streams
        assert sys.stderr in streams


class TestStartBotLoopPipeline:
    """unit: start_bot_loop() pipeline steps are called in the correct order"""

    def test_happy_path_all_steps_called(self):
        """all six startup steps fire on a clean run"""
        with (
            patch.object(nova_core.config, 'on_init') as mock_init,
            patch('shutil.which', return_value='/usr/bin/resvg'),
            patch('nova_core.client._load_event_handlers') as mock_handlers,
            patch.object(nova_core.bot, 'add_application_command') as mock_add,
            patch.object(nova_core.bot, 'load_extension'),
            patch.object(nova_core.bot, 'run') as mock_run,
        ):
            nova_core.start_bot_loop()

            mock_init.assert_called_once()
            mock_handlers.assert_called_once()
            mock_add.assert_called_once()
            mock_run.assert_called_once()

    def test_config_on_init_called_before_dep_check(self):
        """config.on_init() fires before shutil.which is called"""
        call_order = []

        with (
            patch.object(nova_core.config, 'on_init', side_effect=lambda: call_order.append('on_init')),
            patch('shutil.which', side_effect=lambda _: call_order.append('which') or '/usr/bin/resvg'),
            patch('nova_core.client._load_event_handlers'),
            patch.object(nova_core.bot, 'add_application_command'),
            patch.object(nova_core.bot, 'load_extension'),
            patch.object(nova_core.bot, 'run'),
        ):
            nova_core.start_bot_loop()

        assert call_order.index('on_init') < call_order.index('which')

    def test_event_handlers_loaded_before_extensions(self):
        """events module is imported before any extension is loaded"""
        call_order = []

        with (
            patch.object(nova_core.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('nova_core.client._load_event_handlers', side_effect=lambda: call_order.append('events')),
            patch.object(nova_core.bot, 'add_application_command'),
            patch.object(nova_core.bot, 'load_extension', side_effect=lambda _: call_order.append('ext')),
            patch.object(nova_core.bot, 'run'),
        ):
            nova_core.start_bot_loop()

        assert call_order[0] == 'events'
        assert all(v == 'ext' for v in call_order[1:])

    def test_bot_run_called_with_token(self):
        """bot.run() receives config.bot_token"""
        run_value = secrets.token_hex(16)
        nova_core.config.bot_token = run_value

        with (
            patch.object(nova_core.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('nova_core.client._load_event_handlers'),
            patch.object(nova_core.bot, 'add_application_command'),
            patch.object(nova_core.bot, 'load_extension'),
            patch.object(nova_core.bot, 'run') as mock_run,
        ):
            nova_core.start_bot_loop()

        mock_run.assert_called_once_with(run_value)


# ============================================================
# _check_deps()
# ============================================================


class TestCheckDeps:
    """unit: _check_deps() raises on missing dependency, passes when both present"""

    def test_passes_when_both_deps_present(self):
        with patch('shutil.which', return_value='/usr/bin/resvg'):
            nova_core._check_deps()  # should not raise

    def test_raises_when_resvg_missing(self):
        def fake_which(cmd):
            return None if cmd == 'resvg' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: resvg'):
            nova_core._check_deps()

    def test_raises_when_mongodump_missing(self):
        def fake_which(cmd):
            return None if cmd == 'mongodump' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: mongodump'):
            nova_core._check_deps()

    def test_both_checked(self):
        """both resvg and mongodump are checked"""
        checked = []
        with patch('shutil.which', side_effect=lambda cmd: checked.append(cmd) or f'/usr/{cmd}'):
            nova_core._check_deps()
        assert 'resvg' in checked
        assert 'mongodump' in checked

    def test_dep_check_raises_before_bot_run(self):
        """if a dep is missing, bot.run is never called"""
        with (
            patch.object(nova_core.config, 'on_init'),
            patch('shutil.which', return_value=None),
            patch.object(nova_core.bot, 'run') as mock_run,
            pytest.raises(Exception),
        ):
            nova_core.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _load_extensions()
# ============================================================


class TestLoadExtensions:
    """unit: _load_extensions() loads all extensions in order and exits on failure"""

    def test_all_extensions_loaded_in_order(self):
        """all extensions are loaded in the declared order"""
        with patch.object(nova_core.bot, 'load_extension') as mock_load:
            nova_core._load_extensions()

        assert mock_load.call_count == 13
        mock_load.assert_has_calls(
            [
                call('nova_core.commands.cc_stars'),
                call('nova_core.commands.debug'),
                call('nova_core.commands.eggs'),
                call('nova_core.commands.fix'),
                call('nova_core.commands.link'),
                call('nova_core.commands.marker'),
                call('nova_core.commands.query'),
                call('nova_core.commands.remind'),
                call('nova_core.commands.stars'),
                call('nova_core.commands.time'),
                call('nova_core.commands.trees'),
                call('nova_core.commands.wiki'),
                call('nova_core.commands.year'),
            ],
            any_order=False,
        )

    def test_extension_load_failure_raises(self):
        """a failed extension load propagates the exception from _load_extensions"""
        with (
            patch.object(nova_core.bot, 'load_extension', side_effect=Exception('bad ext')),
            pytest.raises(Exception, match='bad ext'),
        ):
            nova_core._load_extensions()

    def test_start_bot_loop_extension_failure_calls_sys_exit_1(self):
        """start_bot_loop catches extension failure and calls sys.exit(1)"""
        with (
            patch.object(nova_core.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('nova_core.client._load_event_handlers'),
            patch.object(nova_core.bot, 'add_application_command'),
            patch.object(nova_core.bot, 'load_extension', side_effect=Exception('bad ext')),
            patch.object(nova_core.bot, 'run'),
            patch('sys.exit') as mock_exit,
        ):
            nova_core.start_bot_loop()

        mock_exit.assert_called_once_with(1)

    def test_remaining_extensions_not_loaded_after_failure(self):
        """loading stops after the first failing extension"""
        load_calls = []

        def fake_load(ext):
            load_calls.append(ext)
            if ext == 'nova_core.commands.fix':
                raise Exception('injected failure')

        with (
            patch.object(nova_core.bot, 'load_extension', side_effect=fake_load),
            pytest.raises(Exception),
        ):
            nova_core._load_extensions()

        # debug loaded fine, fix failed - nothing after
        assert 'nova_core.commands.debug' in load_calls
        assert 'nova_core.commands.fix' in load_calls
        assert 'nova_core.commands.marker' not in load_calls

    def test_bot_run_not_called_when_extension_fails(self):
        """if extensions fail, bot.run is never reached from start_bot_loop"""
        with (
            patch.object(nova_core.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('nova_core.client._load_event_handlers'),
            patch.object(nova_core.bot, 'add_application_command'),
            patch.object(nova_core.bot, 'load_extension', side_effect=Exception('load error')),
            patch.object(nova_core.bot, 'run') as mock_run,
            patch('sys.exit'),
        ):
            nova_core.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _register_core_commands()
# ============================================================


class TestRegisterCoreCommands:
    """unit: _register_core_commands() adds the ping command"""

    def test_adds_one_command(self):
        with patch.object(nova_core.bot, 'add_application_command') as mock_add:
            nova_core._register_core_commands()

        mock_add.assert_called_once()

    def test_adds_ping_command(self):
        """the registered command is the module-level command_ping"""
        with patch.object(nova_core.bot, 'add_application_command') as mock_add:
            nova_core._register_core_commands()

        # the argument passed should be the same object as nova_core.command_ping
        args, _ = mock_add.call_args
        assert args[0] is nova_core.command_ping


# ============================================================
# extensions_list
# ============================================================


class TestEventHandlerModules:
    """unit: every event handler module can be imported without errors.

    this is the compensation test for the mocked _load_event_handlers calls in
    TestStartBotLoopPipeline - those tests verify orchestration only; this test verifies the
    real modules are importable. decorators (@bot.listen) are evaluated at import time, so any
    bad attribute reference or missing import raises here immediately.
    """

    @pytest.mark.parametrize(
        'module',
        [
            'nova_core.client.events',
            'nova_core.client.modlog',
        ],
    )
    def test_event_handler_module_imports_cleanly(self, module):
        import importlib

        importlib.import_module(module)


class TestExtensionImports:
    """unit: every extension module in extensions_list can be imported without errors.

    this is the compensation test for the mocked load_extension calls in TestLoadExtensions -
    those tests verify orchestration only; this test verifies the modules themselves are
    importable. decorators are evaluated at import time, so any bad attribute reference,
    missing import, or module-level crash raises here immediately.
    """

    @pytest.mark.parametrize('ext', nova_core.extensions_list)
    def test_extension_imports_cleanly(self, ext):
        import importlib

        importlib.import_module(ext)


class TestExtensionsList:
    """unit: extensions_list is complete and ordered"""

    def test_expected_extensions_present(self):
        expected = {
            'nova_core.commands.cc_stars',
            'nova_core.commands.debug',
            'nova_core.commands.eggs',
            'nova_core.commands.fix',
            'nova_core.commands.link',
            'nova_core.commands.marker',
            'nova_core.commands.query',
            'nova_core.commands.remind',
            'nova_core.commands.stars',
            'nova_core.commands.time',
            'nova_core.commands.trees',
            'nova_core.commands.wiki',
            'nova_core.commands.year',
        }
        assert set(nova_core.extensions_list) == expected

    def test_no_duplicates(self):
        assert len(nova_core.extensions_list) == len(set(nova_core.extensions_list))

    def test_count_is_thirteen(self):
        assert len(nova_core.extensions_list) == 13


# ============================================================
# module-level singleton creation
# ============================================================


class TestSingletonCreation:
    """unit: bot, config, db singletons are created at import time"""

    def test_bot_is_discord_bot(self):
        import discord

        assert isinstance(nova_core.bot, discord.Bot)

    def test_config_is_nova_config(self):
        from nova_core.config import NovaConfig

        assert isinstance(nova_core.config, NovaConfig)

    def test_db_is_mongo_storage(self):
        from nova_core.database.connection import MongoStorage

        assert isinstance(nova_core.db, MongoStorage)

    def test_command_ping_exists(self):
        assert nova_core.command_ping is not None

    def test_extensions_list_is_not_empty(self):
        assert len(nova_core.extensions_list) > 0
