"""
AttuBot - start_bot_loop() Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Fast, offline tests for the pre-network startup pipeline in doom_bot/__init__.py.
No real Discord connection, no MongoDB, no filesystem access needed.
"""

import secrets
from unittest.mock import call, patch

import pytest

import doom_bot


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
        patch.object(doom_bot.config, 'on_init'),
        patch('shutil.which', return_value=which_return, side_effect=which_side_effect),
        patch('doom_bot.client._load_event_handlers'),
        patch.object(doom_bot.bot, 'add_application_command'),
        patch.object(doom_bot.bot, 'load_extension', side_effect=load_ext_side_effect),
        patch.object(doom_bot.bot, 'run'),
    )


# ============================================================
# start_bot_loop() - full pipeline
# ============================================================


class TestSetupDiscordLogging:
    """unit: _setup_discord_logging() bridges pycord rate-limit logs to the project logger"""

    def test_attaches_handler_to_discord_http_logger(self):
        """a PycordBridgeHandler is added to the discord.http stdlib logger"""
        import logging as _logging

        from doom_bot.logging import PycordBridgeHandler

        discord_http_logger = _logging.getLogger('discord.http')
        initial_count = len(discord_http_logger.handlers)

        doom_bot._setup_discord_logging()

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

        doom_bot._setup_discord_logging()

        assert discord_http_logger.level == _logging.DEBUG

        # cleanup
        discord_http_logger.setLevel(original_level)
        from doom_bot.logging import PycordBridgeHandler

        for h in list(discord_http_logger.handlers):
            if isinstance(h, PycordBridgeHandler):
                discord_http_logger.removeHandler(h)

    def test_root_logger_has_dual_stream_handlers(self):
        """structlog config installs one stdout (< WARNING) and one stderr (>= WARNING) handler on root.

        compensates for PycordBridgeHandler no longer routing records itself; the real stdout/stderr
        split now lives on the root logger via doom_bot.logging._configure().
        """
        import logging as _logging
        import sys

        import doom_bot.logging  # noqa: F401 - imported for side effect of _configure()

        root = _logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_doom_bot_owned', False)]

        assert len(owned) >= 2, f'expected at least 2 doom_bot-owned handlers, got {len(owned)}'

        streams = {h.stream for h in owned if isinstance(h, _logging.StreamHandler)}
        assert sys.stdout in streams
        assert sys.stderr in streams


class TestStartBotLoopPipeline:
    """unit: start_bot_loop() pipeline steps are called in the correct order"""

    def test_happy_path_all_steps_called(self):
        """all six startup steps fire on a clean run"""
        with (
            patch.object(doom_bot.config, 'on_init') as mock_init,
            patch('shutil.which', return_value='/usr/bin/resvg'),
            patch('doom_bot.client._load_event_handlers') as mock_handlers,
            patch.object(doom_bot.bot, 'add_application_command') as mock_add,
            patch.object(doom_bot.bot, 'load_extension'),
            patch.object(doom_bot.bot, 'run') as mock_run,
        ):
            doom_bot.start_bot_loop()

            mock_init.assert_called_once()
            mock_handlers.assert_called_once()
            mock_add.assert_called_once()
            mock_run.assert_called_once()

    def test_config_on_init_called_before_dep_check(self):
        """config.on_init() fires before shutil.which is called"""
        call_order = []

        with (
            patch.object(doom_bot.config, 'on_init', side_effect=lambda: call_order.append('on_init')),
            patch('shutil.which', side_effect=lambda _: call_order.append('which') or '/usr/bin/resvg'),
            patch('doom_bot.client._load_event_handlers'),
            patch.object(doom_bot.bot, 'add_application_command'),
            patch.object(doom_bot.bot, 'load_extension'),
            patch.object(doom_bot.bot, 'run'),
        ):
            doom_bot.start_bot_loop()

        assert call_order.index('on_init') < call_order.index('which')

    def test_event_handlers_loaded_before_extensions(self):
        """events module is imported before any extension is loaded"""
        call_order = []

        with (
            patch.object(doom_bot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('doom_bot.client._load_event_handlers', side_effect=lambda: call_order.append('events')),
            patch.object(doom_bot.bot, 'add_application_command'),
            patch.object(doom_bot.bot, 'load_extension', side_effect=lambda _: call_order.append('ext')),
            patch.object(doom_bot.bot, 'run'),
        ):
            doom_bot.start_bot_loop()

        assert call_order[0] == 'events'
        assert all(v == 'ext' for v in call_order[1:])

    def test_bot_run_called_with_token(self):
        """bot.run() receives config.bot_token"""
        run_value = secrets.token_hex(16)
        doom_bot.config.bot_token = run_value

        with (
            patch.object(doom_bot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('doom_bot.client._load_event_handlers'),
            patch.object(doom_bot.bot, 'add_application_command'),
            patch.object(doom_bot.bot, 'load_extension'),
            patch.object(doom_bot.bot, 'run') as mock_run,
        ):
            doom_bot.start_bot_loop()

        mock_run.assert_called_once_with(run_value)


# ============================================================
# _check_deps()
# ============================================================


class TestCheckDeps:
    """unit: _check_deps() raises on missing dependency, passes when both present"""

    def test_passes_when_both_deps_present(self):
        with patch('shutil.which', return_value='/usr/bin/resvg'):
            doom_bot._check_deps()  # should not raise

    def test_raises_when_resvg_missing(self):
        def fake_which(cmd):
            return None if cmd == 'resvg' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: resvg'):
            doom_bot._check_deps()

    def test_raises_when_mongodump_missing(self):
        def fake_which(cmd):
            return None if cmd == 'mongodump' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: mongodump'):
            doom_bot._check_deps()

    def test_both_checked(self):
        """both resvg and mongodump are checked"""
        checked = []
        with patch('shutil.which', side_effect=lambda cmd: checked.append(cmd) or f'/usr/{cmd}'):
            doom_bot._check_deps()
        assert 'resvg' in checked
        assert 'mongodump' in checked

    def test_dep_check_raises_before_bot_run(self):
        """if a dep is missing, bot.run is never called"""
        with (
            patch.object(doom_bot.config, 'on_init'),
            patch('shutil.which', return_value=None),
            patch.object(doom_bot.bot, 'run') as mock_run,
            pytest.raises(Exception),
        ):
            doom_bot.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _load_extensions()
# ============================================================


class TestLoadExtensions:
    """unit: _load_extensions() loads all extensions in order and exits on failure"""

    def test_all_extensions_loaded_in_order(self):
        """all extensions are loaded in the declared order"""
        with patch.object(doom_bot.bot, 'load_extension') as mock_load:
            doom_bot._load_extensions()

        assert mock_load.call_count == 12
        mock_load.assert_has_calls(
            [
                call('doom_bot.commands.debug'),
                call('doom_bot.commands.eggs'),
                call('doom_bot.commands.fix'),
                call('doom_bot.commands.link'),
                call('doom_bot.commands.marker'),
                call('doom_bot.commands.query'),
                call('doom_bot.commands.remind'),
                call('doom_bot.commands.stars'),
                call('doom_bot.commands.time'),
                call('doom_bot.commands.trees'),
                call('doom_bot.commands.wiki'),
                call('doom_bot.commands.year'),
            ],
            any_order=False,
        )

    def test_extension_load_failure_raises(self):
        """a failed extension load propagates the exception from _load_extensions"""
        with (
            patch.object(doom_bot.bot, 'load_extension', side_effect=Exception('bad ext')),
            pytest.raises(Exception, match='bad ext'),
        ):
            doom_bot._load_extensions()

    def test_start_bot_loop_extension_failure_calls_sys_exit_1(self):
        """start_bot_loop catches extension failure and calls sys.exit(1)"""
        with (
            patch.object(doom_bot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('doom_bot.client._load_event_handlers'),
            patch.object(doom_bot.bot, 'add_application_command'),
            patch.object(doom_bot.bot, 'load_extension', side_effect=Exception('bad ext')),
            patch.object(doom_bot.bot, 'run'),
            patch('sys.exit') as mock_exit,
        ):
            doom_bot.start_bot_loop()

        mock_exit.assert_called_once_with(1)

    def test_remaining_extensions_not_loaded_after_failure(self):
        """loading stops after the first failing extension"""
        load_calls = []

        def fake_load(ext):
            load_calls.append(ext)
            if ext == 'doom_bot.commands.fix':
                raise Exception('injected failure')

        with (
            patch.object(doom_bot.bot, 'load_extension', side_effect=fake_load),
            pytest.raises(Exception),
        ):
            doom_bot._load_extensions()

        # debug loaded fine, fix failed - nothing after
        assert 'doom_bot.commands.debug' in load_calls
        assert 'doom_bot.commands.fix' in load_calls
        assert 'doom_bot.commands.marker' not in load_calls

    def test_bot_run_not_called_when_extension_fails(self):
        """if extensions fail, bot.run is never reached from start_bot_loop"""
        with (
            patch.object(doom_bot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('doom_bot.client._load_event_handlers'),
            patch.object(doom_bot.bot, 'add_application_command'),
            patch.object(doom_bot.bot, 'load_extension', side_effect=Exception('load error')),
            patch.object(doom_bot.bot, 'run') as mock_run,
            patch('sys.exit'),
        ):
            doom_bot.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _register_core_commands()
# ============================================================


class TestRegisterCoreCommands:
    """unit: _register_core_commands() adds the ping command"""

    def test_adds_one_command(self):
        with patch.object(doom_bot.bot, 'add_application_command') as mock_add:
            doom_bot._register_core_commands()

        mock_add.assert_called_once()

    def test_adds_ping_command(self):
        """the registered command is the module-level command_ping"""
        with patch.object(doom_bot.bot, 'add_application_command') as mock_add:
            doom_bot._register_core_commands()

        # the argument passed should be the same object as doom_bot.command_ping
        args, _ = mock_add.call_args
        assert args[0] is doom_bot.command_ping


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
            'doom_bot.client.events',
            'doom_bot.client.modlog',
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

    @pytest.mark.parametrize('ext', doom_bot.extensions_list)
    def test_extension_imports_cleanly(self, ext):
        import importlib

        importlib.import_module(ext)


class TestExtensionsList:
    """unit: extensions_list is complete and ordered"""

    def test_expected_extensions_present(self):
        expected = {
            'doom_bot.commands.debug',
            'doom_bot.commands.eggs',
            'doom_bot.commands.fix',
            'doom_bot.commands.link',
            'doom_bot.commands.marker',
            'doom_bot.commands.query',
            'doom_bot.commands.remind',
            'doom_bot.commands.stars',
            'doom_bot.commands.time',
            'doom_bot.commands.trees',
            'doom_bot.commands.wiki',
            'doom_bot.commands.year',
        }
        assert set(doom_bot.extensions_list) == expected

    def test_no_duplicates(self):
        assert len(doom_bot.extensions_list) == len(set(doom_bot.extensions_list))

    def test_count_is_twelve(self):
        assert len(doom_bot.extensions_list) == 12


# ============================================================
# module-level singleton creation
# ============================================================


class TestSingletonCreation:
    """unit: bot, config, db singletons are created at import time"""

    def test_bot_is_discord_bot(self):
        import discord

        assert isinstance(doom_bot.bot, discord.Bot)

    def test_config_is_nova_config(self):
        from doom_bot.config import NovaConfig

        assert isinstance(doom_bot.config, NovaConfig)

    def test_db_is_mongo_storage(self):
        from doom_bot.database.connection import MongoStorage

        assert isinstance(doom_bot.db, MongoStorage)

    def test_command_ping_exists(self):
        assert doom_bot.command_ping is not None

    def test_extensions_list_is_not_empty(self):
        assert len(doom_bot.extensions_list) > 0
