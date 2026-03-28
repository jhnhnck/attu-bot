"""
AttuBot - start_bot_loop() Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Fast, offline tests for the pre-network startup pipeline in attubot/__init__.py.
No real Discord connection, no MongoDB, no filesystem access needed.
"""

import secrets
from unittest.mock import call, patch

import pytest

import attubot


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
        patch.object(attubot.config, 'on_init'),
        patch('shutil.which', return_value=which_return, side_effect=which_side_effect),
        patch('attubot.client._load_event_handlers'),
        patch.object(attubot.bot, 'add_application_command'),
        patch.object(attubot.bot, 'load_extension', side_effect=load_ext_side_effect),
        patch.object(attubot.bot, 'run'),
    )


# ============================================================
# start_bot_loop() - full pipeline
# ============================================================


class TestStartBotLoopPipeline:
    """unit: start_bot_loop() pipeline steps are called in the correct order"""

    def test_happy_path_all_steps_called(self):
        """all six startup steps fire on a clean run"""
        with (
            patch.object(attubot.config, 'on_init') as mock_init,
            patch('shutil.which', return_value='/usr/bin/resvg'),
            patch('attubot.client._load_event_handlers') as mock_handlers,
            patch.object(attubot.bot, 'add_application_command') as mock_add,
            patch.object(attubot.bot, 'load_extension'),
            patch.object(attubot.bot, 'run') as mock_run,
        ):
            attubot.start_bot_loop()

            mock_init.assert_called_once()
            mock_handlers.assert_called_once()
            mock_add.assert_called_once()
            mock_run.assert_called_once()

    def test_config_on_init_called_before_dep_check(self):
        """config.on_init() fires before shutil.which is called"""
        call_order = []

        with (
            patch.object(attubot.config, 'on_init', side_effect=lambda: call_order.append('on_init')),
            patch('shutil.which', side_effect=lambda _: call_order.append('which') or '/usr/bin/resvg'),
            patch('attubot.client._load_event_handlers'),
            patch.object(attubot.bot, 'add_application_command'),
            patch.object(attubot.bot, 'load_extension'),
            patch.object(attubot.bot, 'run'),
        ):
            attubot.start_bot_loop()

        assert call_order.index('on_init') < call_order.index('which')

    def test_event_handlers_loaded_before_extensions(self):
        """events module is imported before any extension is loaded"""
        call_order = []

        with (
            patch.object(attubot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('attubot.client._load_event_handlers', side_effect=lambda: call_order.append('events')),
            patch.object(attubot.bot, 'add_application_command'),
            patch.object(attubot.bot, 'load_extension', side_effect=lambda _: call_order.append('ext')),
            patch.object(attubot.bot, 'run'),
        ):
            attubot.start_bot_loop()

        assert call_order[0] == 'events'
        assert all(v == 'ext' for v in call_order[1:])

    def test_bot_run_called_with_token(self):
        """bot.run() receives config.bot_token"""
        run_value = secrets.token_hex(16)
        attubot.config.bot_token = run_value

        with (
            patch.object(attubot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('attubot.client._load_event_handlers'),
            patch.object(attubot.bot, 'add_application_command'),
            patch.object(attubot.bot, 'load_extension'),
            patch.object(attubot.bot, 'run') as mock_run,
        ):
            attubot.start_bot_loop()

        mock_run.assert_called_once_with(run_value)


# ============================================================
# _check_deps()
# ============================================================


class TestCheckDeps:
    """unit: _check_deps() raises on missing dependency, passes when both present"""

    def test_passes_when_both_deps_present(self):
        with patch('shutil.which', return_value='/usr/bin/resvg'):
            attubot._check_deps()  # should not raise

    def test_raises_when_resvg_missing(self):
        def fake_which(cmd):
            return None if cmd == 'resvg' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: resvg'):
            attubot._check_deps()

    def test_raises_when_mongodump_missing(self):
        def fake_which(cmd):
            return None if cmd == 'mongodump' else f'/usr/bin/{cmd}'

        with patch('shutil.which', side_effect=fake_which), pytest.raises(Exception, match='missing dependency: mongodump'):
            attubot._check_deps()

    def test_both_checked(self):
        """both resvg and mongodump are checked"""
        checked = []
        with patch('shutil.which', side_effect=lambda cmd: checked.append(cmd) or f'/usr/{cmd}'):
            attubot._check_deps()
        assert 'resvg' in checked
        assert 'mongodump' in checked

    def test_dep_check_raises_before_bot_run(self):
        """if a dep is missing, bot.run is never called"""
        with (
            patch.object(attubot.config, 'on_init'),
            patch('shutil.which', return_value=None),
            patch.object(attubot.bot, 'run') as mock_run,
            pytest.raises(Exception),
        ):
            attubot.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _load_extensions()
# ============================================================


class TestLoadExtensions:
    """unit: _load_extensions() loads all extensions in order and exits on failure"""

    def test_all_ten_extensions_loaded_in_order(self):
        """all ten extensions are loaded in the declared order"""
        with patch.object(attubot.bot, 'load_extension') as mock_load:
            attubot._load_extensions()

        assert mock_load.call_count == 10
        mock_load.assert_has_calls(
            [
                call('attubot.commands.chat'),
                call('attubot.commands.debug'),
                call('attubot.commands.fix'),
                call('attubot.commands.link'),
                call('attubot.commands.marker'),
                call('attubot.commands.query'),
                call('attubot.commands.stars'),
                call('attubot.commands.time'),
                call('attubot.commands.wiki'),
                call('attubot.commands.year'),
            ],
            any_order=False,
        )

    def test_extension_load_failure_raises(self):
        """a failed extension load propagates the exception from _load_extensions"""
        with (
            patch.object(attubot.bot, 'load_extension', side_effect=Exception('bad ext')),
            pytest.raises(Exception, match='bad ext'),
        ):
            attubot._load_extensions()

    def test_start_bot_loop_extension_failure_calls_sys_exit_1(self):
        """start_bot_loop catches extension failure and calls sys.exit(1)"""
        with (
            patch.object(attubot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('attubot.client._load_event_handlers'),
            patch.object(attubot.bot, 'add_application_command'),
            patch.object(attubot.bot, 'load_extension', side_effect=Exception('bad ext')),
            patch.object(attubot.bot, 'run'),
            patch('sys.exit') as mock_exit,
        ):
            attubot.start_bot_loop()

        mock_exit.assert_called_once_with(1)

    def test_remaining_extensions_not_loaded_after_failure(self):
        """loading stops after the first failing extension"""
        load_calls = []

        def fake_load(ext):
            load_calls.append(ext)
            if ext == 'attubot.commands.fix':
                raise Exception('injected failure')

        with (
            patch.object(attubot.bot, 'load_extension', side_effect=fake_load),
            pytest.raises(Exception),
        ):
            attubot._load_extensions()

        # debug loaded fine, fix failed - nothing after
        assert 'attubot.commands.debug' in load_calls
        assert 'attubot.commands.fix' in load_calls
        assert 'attubot.commands.marker' not in load_calls

    def test_bot_run_not_called_when_extension_fails(self):
        """if extensions fail, bot.run is never reached from start_bot_loop"""
        with (
            patch.object(attubot.config, 'on_init'),
            patch('shutil.which', return_value='/usr/bin/cmd'),
            patch('attubot.client._load_event_handlers'),
            patch.object(attubot.bot, 'add_application_command'),
            patch.object(attubot.bot, 'load_extension', side_effect=Exception('load error')),
            patch.object(attubot.bot, 'run') as mock_run,
            patch('sys.exit'),
        ):
            attubot.start_bot_loop()

        mock_run.assert_not_called()


# ============================================================
# _register_core_commands()
# ============================================================


class TestRegisterCoreCommands:
    """unit: _register_core_commands() adds the ping command"""

    def test_adds_one_command(self):
        with patch.object(attubot.bot, 'add_application_command') as mock_add:
            attubot._register_core_commands()

        mock_add.assert_called_once()

    def test_adds_ping_command(self):
        """the registered command is the module-level command_ping"""
        with patch.object(attubot.bot, 'add_application_command') as mock_add:
            attubot._register_core_commands()

        # the argument passed should be the same object as attubot.command_ping
        args, _ = mock_add.call_args
        assert args[0] is attubot.command_ping


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
            'attubot.client.events',
            'attubot.client.modlog',
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

    @pytest.mark.parametrize('ext', attubot.extensions_list)
    def test_extension_imports_cleanly(self, ext):
        import importlib

        importlib.import_module(ext)


class TestExtensionsList:
    """unit: extensions_list is complete and ordered"""

    def test_expected_extensions_present(self):
        expected = {
            'attubot.commands.chat',
            'attubot.commands.debug',
            'attubot.commands.fix',
            'attubot.commands.link',
            'attubot.commands.marker',
            'attubot.commands.query',
            'attubot.commands.stars',
            'attubot.commands.time',
            'attubot.commands.wiki',
            'attubot.commands.year',
        }
        assert set(attubot.extensions_list) == expected

    def test_no_duplicates(self):
        assert len(attubot.extensions_list) == len(set(attubot.extensions_list))

    def test_count_is_ten(self):
        assert len(attubot.extensions_list) == 10


# ============================================================
# module-level singleton creation
# ============================================================


class TestSingletonCreation:
    """unit: bot, config, db singletons are created at import time"""

    def test_bot_is_discord_bot(self):
        import discord

        assert isinstance(attubot.bot, discord.Bot)

    def test_config_is_nova_config(self):
        from attubot.config import NovaConfig

        assert isinstance(attubot.config, NovaConfig)

    def test_db_is_mongo_storage(self):
        from attubot.database.connection import MongoStorage

        assert isinstance(attubot.db, MongoStorage)

    def test_command_ping_exists(self):
        assert attubot.command_ping is not None

    def test_extensions_list_is_not_empty(self):
        assert len(attubot.extensions_list) > 0
