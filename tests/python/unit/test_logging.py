"""
AttuBot - nova_core.logging Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Covers the AttubotLogger wrapper, _resolve_pycord_bucket processor, _MaxLevelFilter,
and _configure idempotency. Uses structlog.testing.capture_logs to assert event_dicts.
"""

import logging

import pytest

from nova_core.logging import ALERT, TRACE, AttubotLogger, _configure, _MaxLevelFilter, _resolve_pycord_bucket


pytestmark = pytest.mark.unit


# ============================================================
# AttubotLogger wrapper
# ============================================================


class TestAttubotLogger:
    """unit: legacy method names route to the right structlog level"""

    def test_warn_routes_to_warning(self, capture_structlog):
        AttubotLogger('test.warn').warn('something off')

        assert len(capture_structlog) == 1
        assert capture_structlog[0]['event'] == 'something off'
        assert capture_structlog[0]['log_level'] == 'warning'

    def test_fatal_routes_to_critical(self, capture_structlog):
        AttubotLogger('test.fatal').fatal('terminal')

        assert capture_structlog[0]['log_level'] == 'critical'

    def test_join_handles_varargs_like_print(self, capture_structlog):
        """logger.debug(*pages) at commands/wiki.py joins args with spaces"""
        AttubotLogger('test.varargs').error('a', 'b', 'c')

        assert capture_structlog[0]['event'] == 'a b c'

    def test_kwargs_pass_through_as_event_fields(self, capture_structlog):
        AttubotLogger('test.kw').info('hello', user_id=42, guild_id=99)

        assert capture_structlog[0]['user_id'] == 42
        assert capture_structlog[0]['guild_id'] == 99

    def test_trace_silent_without_debug_env(self, monkeypatch, capture_structlog):
        monkeypatch.delenv('DEBUG', raising=False)
        # the gate is read at module import; rebind the module flag for this test
        import nova_core.logging as logging_mod

        monkeypatch.setattr(logging_mod, '_DEBUG_MODE', False)

        AttubotLogger('test.trace').trace('should not appear')
        AttubotLogger('test.trace').alert('should not appear')
        AttubotLogger('test.trace').debug('should not appear')

        assert capture_structlog == []

    def test_trace_emits_when_debug_set(self, monkeypatch, capture_structlog):
        import nova_core.logging as logging_mod

        monkeypatch.setattr(logging_mod, '_DEBUG_MODE', True)
        # capture_logs intercepts structlog calls but not stdlib direct calls; trace/alert
        # route through stdlib because TRACE/ALERT are outside structlog's level table.
        # use stdlib caplog-style assertion via the structured testing handler instead.
        with pytest.MonkeyPatch.context() as mp:
            recorded: list[tuple[int, str]] = []
            mp.setattr(
                logging_mod.logging.getLogger('test.trace'),
                'log',
                lambda level, msg, **kw: recorded.append((level, msg)),
            )
            AttubotLogger('test.trace').trace('hello trace')

        assert recorded == [(TRACE, 'hello trace')]


# ============================================================
# _resolve_pycord_bucket processor
# ============================================================


class TestResolvePycordBucket:
    """unit: foreign_pre_chain processor for pycord rate-limit logs"""

    def test_substitutes_channel_id_when_present(self):
        ev = {
            'logger': 'discord.http',
            'event': 'rate limit hit "1234:None:/channels/{channel_id}/messages"',
        }
        out = _resolve_pycord_bucket(None, None, ev)
        assert '/channels/1234/messages' in out['event']

    def test_substitutes_guild_id_when_present(self):
        ev = {
            'logger': 'discord.http',
            'event': 'rate limit "None:5678:/guilds/{guild_id}/members"',
        }
        out = _resolve_pycord_bucket(None, None, ev)
        assert '/guilds/5678/members' in out['event']

    def test_strips_unresolved_placeholders(self):
        ev = {
            'logger': 'discord.http',
            'event': '"None:None:/channels/{channel_id}/messages/{message_id}"',
        }
        out = _resolve_pycord_bucket(None, None, ev)
        assert '{channel_id}' not in out['event']
        assert '{message_id}' not in out['event']

    def test_skips_non_discord_records(self):
        ev = {'logger': 'nova_core.client.events', 'event': 'unrelated'}
        out = _resolve_pycord_bucket(None, None, ev)
        assert out is ev  # unchanged

    def test_skips_records_without_bucket_format(self):
        ev = {'logger': 'discord.http', 'event': 'hello world'}
        out = _resolve_pycord_bucket(None, None, ev)
        assert out['event'] == 'hello world'

    def test_skips_when_event_not_a_string(self):
        ev = {'logger': 'discord.http', 'event': 42}
        out = _resolve_pycord_bucket(None, None, ev)
        assert out is ev


# ============================================================
# _MaxLevelFilter
# ============================================================


class TestMaxLevelFilter:
    """unit: stdlib filter that admits only records strictly below max_level"""

    def _make_record(self, levelno: int) -> logging.LogRecord:
        return logging.LogRecord('x', levelno, 'p', 0, 'm', None, None)

    def test_admits_below_max(self):
        f = _MaxLevelFilter(logging.WARNING)
        assert f.filter(self._make_record(logging.INFO)) is True
        assert f.filter(self._make_record(logging.DEBUG)) is True

    def test_rejects_at_or_above_max(self):
        f = _MaxLevelFilter(logging.WARNING)
        assert f.filter(self._make_record(logging.WARNING)) is False
        assert f.filter(self._make_record(logging.ERROR)) is False
        assert f.filter(self._make_record(logging.CRITICAL)) is False

    def test_admits_custom_levels_below(self):
        f = _MaxLevelFilter(logging.WARNING)
        assert f.filter(self._make_record(TRACE)) is True
        assert f.filter(self._make_record(ALERT)) is True


# ============================================================
# discord.http level gating
# ============================================================


class TestDiscordHttpLevelGating:
    """unit: _setup_discord_logging respects the DEBUG env var"""

    def _reset_discord_http(self):
        from nova_core.logging import PycordBridgeHandler

        log = logging.getLogger('discord.http')
        log.setLevel(logging.NOTSET)
        log.handlers = [h for h in log.handlers if not isinstance(h, PycordBridgeHandler)]

    def test_pinned_to_warning_when_debug_unset(self, monkeypatch):
        from nova_core.client import _setup_discord_logging

        monkeypatch.delenv('DEBUG', raising=False)
        self._reset_discord_http()
        _setup_discord_logging()
        assert logging.getLogger('discord.http').level == logging.WARNING

    def test_set_to_debug_when_debug_present(self, monkeypatch):
        from nova_core.client import _setup_discord_logging

        monkeypatch.setenv('DEBUG', '1')
        self._reset_discord_http()
        _setup_discord_logging()
        assert logging.getLogger('discord.http').level == logging.DEBUG


# ============================================================
# _configure idempotency
# ============================================================


class TestConfigureIdempotent:
    """unit: re-importing or re-calling _configure() does not duplicate handlers"""

    def test_repeated_calls_do_not_duplicate_handlers(self):
        root = logging.getLogger()
        before = [h for h in root.handlers if getattr(h, '_nova_core_owned', False)]

        _configure()
        _configure()
        _configure()

        after = [h for h in root.handlers if getattr(h, '_nova_core_owned', False)]
        assert len(after) == len(before), f'expected handler count unchanged, was {len(before)} now {len(after)}'

    def test_owned_handlers_split_stdout_and_stderr(self):
        import sys

        _configure()
        root = logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_nova_core_owned', False)]
        streams = {h.stream for h in owned if isinstance(h, logging.StreamHandler)}
        assert sys.stdout in streams
        assert sys.stderr in streams
