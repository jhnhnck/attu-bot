"""
AttuBot - attu_logging Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Covers _resolve_pycord_bucket, _MaxLevelFilter, and configure() idempotency.
AttubotLogger tests removed in phase 2 (logger migrated to structlog.stdlib directly).
"""

import logging

import pytest

from attu_logging.config import _MaxLevelFilter, _resolve_pycord_bucket
from attu_logging.config import configure as _configure


pytestmark = pytest.mark.unit


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

    def test_admits_sub_debug_levels(self):
        """levels below DEBUG (e.g. custom trace=5, alert=15) still pass the filter"""
        f = _MaxLevelFilter(logging.WARNING)
        assert f.filter(self._make_record(5)) is True   # former TRACE
        assert f.filter(self._make_record(15)) is True  # former ALERT


# ============================================================
# discord.http level gating
# ============================================================


class TestDiscordHttpLevelGating:
    """unit: _setup_discord_logging respects the DEBUG env var"""

    def _reset_discord_http(self):
        from nova_core.client import PycordBridgeHandler

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
# configure() idempotency
# ============================================================


class TestConfigureIdempotent:
    """unit: re-importing or re-calling configure() does not duplicate handlers"""

    def test_repeated_calls_do_not_duplicate_handlers(self):
        root = logging.getLogger()
        before = [h for h in root.handlers if getattr(h, '_attu_owned', False)]

        _configure()
        _configure()
        _configure()

        after = [h for h in root.handlers if getattr(h, '_attu_owned', False)]
        assert len(after) == len(before), f'expected handler count unchanged, was {len(before)} now {len(after)}'

    def test_owned_handlers_split_stdout_and_stderr(self):
        import sys

        _configure()
        root = logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_attu_owned', False)]
        streams = {h.stream for h in owned if isinstance(h, logging.StreamHandler)}
        assert sys.stdout in streams
        assert sys.stderr in streams
