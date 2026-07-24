# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_feature_loader | tests for FeatureContext loader."""

import os
import sys
import time as _time
import types


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


# --- load_feature wiring ---


class TestLoadFeatureWiring:
    def test_tasks_registered(self):
        """tasks in the manifest are registered with the scheduler"""
        from nova_core.loader import FeatureContext
        from nova_core.manifest import FeatureManifest

        scheduler = MagicMock()
        scheduler.registered_tasks.return_value = []
        ctx = FeatureContext(bot=MagicMock(), scheduler=scheduler, config=MagicMock(), db=MagicMock())

        task = MagicMock()
        ctx.load_feature(FeatureManifest(name='t', tasks=[task]))

        scheduler.register.assert_called_once_with(task)

    def test_duplicate_tasks_skipped(self):
        """tasks already in the scheduler are not re-registered"""
        from nova_core.loader import FeatureContext
        from nova_core.manifest import FeatureManifest

        task = MagicMock()
        scheduler = MagicMock()
        scheduler.registered_tasks.return_value = [task]
        ctx = FeatureContext(bot=MagicMock(), scheduler=scheduler, config=MagicMock(), db=MagicMock())

        ctx.load_feature(FeatureManifest(name='t', tasks=[task]))

        scheduler.register.assert_not_called()

    def test_event_handlers_registered_via_add_listener(self):
        """event handlers are registered via bot.add_listener(fn, name=event_name)"""
        from nova_core.loader import FeatureContext
        from nova_core.manifest import FeatureManifest

        bot = MagicMock()
        scheduler = MagicMock()
        scheduler.registered_tasks.return_value = []

        async def handler(message):
            pass

        ctx = FeatureContext(bot=bot, scheduler=scheduler, config=MagicMock(), db=MagicMock())
        ctx.load_feature(FeatureManifest(name='t', event_handlers={'on_message': handler}))

        bot.add_listener.assert_called_once_with(handler, name='on_message')

    def test_setup_fn_called_with_bot(self):
        """setup fn is called with the bot instance"""
        from nova_core.loader import FeatureContext
        from nova_core.manifest import FeatureManifest

        bot = MagicMock()
        scheduler = MagicMock()
        scheduler.registered_tasks.return_value = []
        setup = MagicMock()

        ctx = FeatureContext(bot=bot, scheduler=scheduler, config=MagicMock(), db=MagicMock())
        ctx.load_feature(FeatureManifest(name='t', setup=setup))

        setup.assert_called_once_with(bot)

    def test_none_setup_fn_is_skipped(self):
        """setup=None does not raise"""
        from nova_core.loader import FeatureContext
        from nova_core.manifest import FeatureManifest

        ctx = FeatureContext(bot=MagicMock(), scheduler=MagicMock(), config=MagicMock(), db=MagicMock())
        ctx.scheduler.registered_tasks.return_value = []
        # should not raise
        ctx.load_feature(FeatureManifest(name='t', setup=None))


# --- load_all error handling ---


class TestLoadAllErrors:
    def test_missing_module_logs_warning_no_raise(self, capture_structlog):
        """ImportError on a feature module is caught; warning logged; no exception raised"""
        from nova_core.loader import FeatureContext

        scheduler = MagicMock()
        scheduler.registered_tasks.return_value = []
        ctx = FeatureContext(bot=MagicMock(), scheduler=scheduler, config=MagicMock(), db=MagicMock())

        ctx.load_all(['nova_core.features._does_not_exist_xyzzy'])

        warnings = [e for e in capture_structlog if e.get('log_level') == 'warning']
        assert any('not found' in str(e.get('event', '')) for e in warnings)

    def test_no_manifest_attr_logs_warning_no_raise(self, capture_structlog):
        """module without a manifest attr is caught; warning logged; no exception raised"""
        from nova_core.loader import FeatureContext

        fake_mod = types.ModuleType('nova_core.features._fake_no_manifest_xyz')
        sys.modules['nova_core.features._fake_no_manifest_xyz'] = fake_mod
        try:
            scheduler = MagicMock()
            scheduler.registered_tasks.return_value = []
            ctx = FeatureContext(bot=MagicMock(), scheduler=scheduler, config=MagicMock(), db=MagicMock())

            ctx.load_all(['nova_core.features._fake_no_manifest_xyz'])

            warnings = [e for e in capture_structlog if e.get('log_level') == 'warning']
            assert any('no manifest' in str(e.get('event', '')) for e in warnings)
        finally:
            sys.modules.pop('nova_core.features._fake_no_manifest_xyz', None)

    def test_wrong_type_manifest_logs_warning_no_raise(self, capture_structlog):
        """module with manifest set to a non-FeatureManifest value is caught; warning logged"""
        from nova_core.loader import FeatureContext

        fake_mod = types.ModuleType('nova_core.features._fake_wrong_manifest_xyz')
        fake_mod.manifest = 'not a manifest'  # type: ignore[attr-defined]
        sys.modules['nova_core.features._fake_wrong_manifest_xyz'] = fake_mod
        try:
            scheduler = MagicMock()
            scheduler.registered_tasks.return_value = []
            ctx = FeatureContext(bot=MagicMock(), scheduler=scheduler, config=MagicMock(), db=MagicMock())

            ctx.load_all(['nova_core.features._fake_wrong_manifest_xyz'])

            warnings = [e for e in capture_structlog if e.get('log_level') == 'warning']
            assert any('no manifest' in str(e.get('event', '')) for e in warnings)
        finally:
            sys.modules.pop('nova_core.features._fake_wrong_manifest_xyz', None)
