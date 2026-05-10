# SPDX-License-Identifier: Apache-2.0
"""tests.python.integration.test_attu_logging_contract | phase-0 invariants for attu_logging.configure()."""

import io
import logging
import os
import re

import pytest
import structlog

from attu_logging import configure


# integration-marked because it asserts on cross-package state established by
# conftest's import-time configure() call. unit-marker scope is "no shared state."
pytestmark = pytest.mark.integration

_LEVEL_PREFIX_RE = re.compile(r'^\[(trace|alert|debug|info|warning|error|critical)\s*\]\s+', re.MULTILINE)
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


# ============================================================
# R1 — configure-vs-import timing
# ============================================================


class TestConfigureRanBeforeStructlogBindings:
    """configure() ran before any structlog logger was actually invoked.

    R1 violation shape: a module-level emit happens before configure(), structlog's
    LazyProxy resolves with default config, and that wrapper class is cached for the
    process. asserting against `structlog.get_config()` and the presence of our
    handlers is a more direct test of "did configure win the race" than counting
    handlers; pytest itself attaches LogCapture/LiveLogging handlers to root that
    have nothing to do with our pipeline.
    """

    def test_at_least_one_attu_owned_handler_on_root(self):
        root = logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_attu_owned', False)]
        assert owned, f'no _attu_owned handlers on root; configure() did not run. handlers: {root.handlers!r}'

    def test_structlog_wrapper_is_bound_logger(self):
        cfg = structlog.get_config()
        assert cfg['wrapper_class'] is structlog.stdlib.BoundLogger, f'structlog wrapper_class is {cfg["wrapper_class"]!r}; configure() did not install BoundLogger (R1: a get_logger() emit may have raced configure() and cached defaults)'

    def test_processor_chain_includes_logger_name_and_level(self):
        """sanity: configure()'s structlog processor list is what loggers actually see.

        if a default-config logger was cached first, the processor list here would be
        the structlog defaults rather than ours.
        """
        processors = structlog.get_config()['processors']
        proc_names = {getattr(p, '__name__', type(p).__name__) for p in processors}
        assert 'add_logger_name' in proc_names, f'add_logger_name missing from processor chain: {proc_names!r}'
        assert 'add_log_level' in proc_names, f'add_log_level missing from processor chain: {proc_names!r}'


# ============================================================
# R3 — configure() idempotency
# ============================================================


class TestConfigureIdempotent:
    """re-calling configure() must not duplicate handlers."""

    def test_repeated_calls_do_not_duplicate_handlers(self):
        root = logging.getLogger()
        before = len(root.handlers)

        configure()
        configure()
        configure()

        after = len(root.handlers)
        assert after == before, f'expected handler count {before}, got {after} after three re-calls'

    def test_owned_handlers_split_stdout_and_stderr(self):
        import sys

        root = logging.getLogger()
        owned = [h for h in root.handlers if getattr(h, '_attu_owned', False)]
        streams = {h.stream for h in owned if isinstance(h, logging.StreamHandler)}

        assert sys.stdout in streams, 'no _attu_owned handler points at stdout'
        assert sys.stderr in streams, 'no _attu_owned handler points at stderr'


# ============================================================
# R4 — library-noise pinning
# ============================================================


class TestLibraryNoisePins:
    """noisy third-party loggers stay pinned at WARNING regardless of root level."""

    @pytest.mark.parametrize('name', ['pymongo', 'aiohttp.access', 'discord.gateway'])
    def test_library_pinned_to_warning(self, name):
        level = logging.getLogger(name).level
        assert level == logging.WARNING, f'{name} expected WARNING ({logging.WARNING}), got {logging.getLevelName(level)} ({level})'

    def test_discord_http_gated_on_debug_env(self):
        """discord.http is WARNING by default and DEBUG when the DEBUG env var is set.

        the dev tests container sets DEBUG=1, so this case verifies the gate fires.
        without DEBUG (e.g. host pytest run), the WARNING branch verifies.
        """
        actual = logging.getLogger('discord.http').level
        expected = logging.DEBUG if 'DEBUG' in os.environ else logging.WARNING
        assert actual == expected, f'discord.http level: expected {logging.getLevelName(expected)}, got {logging.getLevelName(actual)} (DEBUG env set: {"DEBUG" in os.environ})'


# ============================================================
# Rendered record shape — pin the contract the container-logs skill relies on
# ============================================================


class TestRenderedRecordShape:
    """records emitted under the default console renderer match `^\\[(level) *\\] `.

    this is the exact shape the `container-logs` skill greps for; if the renderer or
    foreign pre-chain ever changes the prefix shape, the recipe in that skill breaks
    silently. pin the contract here so the break shows up as a unit-fast test failure.
    """

    def test_console_record_starts_with_level_prefix(self):
        root = logging.getLogger()
        # borrow the formatter from an existing _attu_owned handler so the test
        # exercises the real configured pipeline rather than a fresh formatter
        owned = next((h for h in root.handlers if getattr(h, '_attu_owned', False)), None)
        assert owned is not None, 'no _attu_owned root handler to borrow formatter from'

        buf = io.StringIO()
        capture_h = logging.StreamHandler(buf)
        capture_h.setFormatter(owned.formatter)
        capture_h.setLevel(logging.DEBUG)
        root.addHandler(capture_h)
        try:
            log = structlog.stdlib.get_logger('attu_models.connection')
            log.info('mongodb connection established')
        finally:
            root.removeHandler(capture_h)

        rendered = buf.getvalue()
        stripped = _ANSI_RE.sub('', rendered)
        assert _LEVEL_PREFIX_RE.search(stripped), f'rendered record does not match the container-logs grep contract: {stripped!r}'


# ============================================================
# shared-models logger via configure path
# ============================================================


class TestSharedModelsLoggerPath:
    """attu_models loggers go through the configured structlog pipeline."""

    def test_attu_models_connection_logger_routes_through_structlog(self):
        # importing the module also smoke-tests that its module-level
        # `logger = structlog.stdlib.get_logger(__name__)` resolves
        import attu_models.connection  # noqa: F401 - imported for the side effect of binding the module-level logger

        log = structlog.stdlib.get_logger('attu_models.connection')
        with structlog.testing.capture_logs() as captured:
            log.info('hello from attu_models.connection', component='test')

        assert len(captured) == 1, f'expected 1 captured event, got {len(captured)}: {captured!r}'
        assert captured[0]['event'] == 'hello from attu_models.connection'
        assert captured[0]['log_level'] == 'info'
        assert captured[0]['component'] == 'test'

    def test_attu_models_repositories_logger_routes_through_structlog(self):
        # phase-1 invariant: repositories.py was flipped from the wrapper to direct
        # structlog. import smoke-tests the module-level `logger = structlog.stdlib.get_logger(__name__)`
        # resolves; the capture confirms emits land in the configured pipeline.
        import attu_models.repositories  # noqa: F401 - imported for the side effect of binding the module-level logger

        log = structlog.stdlib.get_logger('attu_models.repositories')
        with structlog.testing.capture_logs() as captured:
            log.warning('repository warning under capture', emoji='dot.bad')

        assert len(captured) == 1, f'expected 1 captured event, got {len(captured)}: {captured!r}'
        assert captured[0]['event'] == 'repository warning under capture'
        assert captured[0]['log_level'] == 'warning'
        assert captured[0]['emoji'] == 'dot.bad'
