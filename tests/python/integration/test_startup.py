# SPDX-License-Identifier: Apache-2.0
"""tests.python.integration.test_startup | bot startup integration tests against real MongoDB."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# full _do_ready_init() against real mongo: db handshake, guild load, and
# feature/task registration can plausibly exceed the 10s default on a cold
# container. 30s leaves headroom while still catching a true hang.
pytestmark = [pytest.mark.integration, pytest.mark.timeout(30)]


# --- helpers ---


def _make_fake_app_info(owner_id: int = 222222222222):
    """fake ApplicationInfo with the given owner id"""
    info = MagicMock()
    info.team = None
    info.owner = MagicMock()
    info.owner.id = owner_id
    return info


@contextmanager
def _bot_patched(*, owner_id: int = 222222222222):
    """patches all discord bot network methods used by startup; yields dict of mocks"""
    from nova_core.client.core import bot

    fake_guild = MagicMock()
    fake_guild.name = 'Test Guild'

    with (
        patch.object(bot, 'login', new_callable=AsyncMock) as m_login,
        patch.object(bot, 'sync_commands', new_callable=AsyncMock) as m_sync,
        patch.object(bot, 'application_info', new_callable=AsyncMock, return_value=_make_fake_app_info(owner_id)) as m_info,
        patch.object(bot, 'get_guild', return_value=fake_guild),
        patch.object(bot, 'fetch_guild', new_callable=AsyncMock, return_value=fake_guild),
    ):
        yield {'login': m_login, 'sync_commands': m_sync, 'application_info': m_info}


# --- module-scoped config init ---


@pytest_asyncio.fixture(scope='module')
async def initialized_config():
    """init config from TOML once; teardown closes db"""
    from nova_core.client.core import config

    if not config._get_event('init').is_set():
        config.on_init()

    yield config

    # best-effort cleanup; suppress event-loop mismatch at module teardown
    from nova_core.client.core import db

    try:
        if db.client:
            await db.close()
    except RuntimeError:
        pass  # connection closed with process


# --- per-test state reset ---


def _reset(cfg, *, test_mode: bool = True):
    """reset mutable config state before each integration test run"""
    cfg.test_mode = test_mode
    cfg.web_mode = False
    cfg.owner_ids = set()
    cfg._events['load'].clear()
    cfg._events['ready'].clear()


# ============================================================
# Bot ready path (_do_ready_init)
# ============================================================


class TestBotReadyPath:
    """integration: _do_ready_init() with real mongo and patched discord"""

    async def test_reaches_test_mode_shutdown(self, initialized_config):
        """in test_mode, _shutdown(0) is called after ready"""
        from nova_core.client.events import _do_ready_init

        _reset(initialized_config)
        mock_shutdown = AsyncMock()

        with _bot_patched(), patch('nova_core.client.events._shutdown', mock_shutdown):
            await _do_ready_init()

        mock_shutdown.assert_called_once_with(exit_code=0)

    async def test_config_load_event_set(self, initialized_config):
        """config load event is set after db+config init"""
        from nova_core.client.events import _do_ready_init

        cfg = initialized_config
        _reset(cfg)

        with _bot_patched(), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        assert cfg._get_event('load').is_set()

    async def test_config_ready_event_set(self, initialized_config):
        """config ready event is set after on_ready() completes"""
        from nova_core.client.events import _do_ready_init

        cfg = initialized_config
        _reset(cfg)

        with _bot_patched(), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        assert cfg._get_event('ready').is_set()

    async def test_db_connected(self, initialized_config):
        """init_database() establishes a mongo connection"""
        from nova_core.client.core import db
        from nova_core.client.events import _do_ready_init

        _reset(initialized_config)

        with _bot_patched(), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        assert db.client is not None

    async def test_config_repo_attached(self, initialized_config):
        """config_repo is populated after database init"""
        from nova_core.client.events import _do_ready_init

        cfg = initialized_config
        _reset(cfg)

        with _bot_patched(), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        assert cfg.config_repo is not None

    async def test_owner_ids_populated(self, initialized_config):
        """owner_ids are set from the fake application_info"""
        from nova_core.client.events import _do_ready_init

        cfg = initialized_config
        _reset(cfg)

        with _bot_patched(owner_id=987654321), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        assert 987654321 in cfg.owner_ids

    async def test_guilds_loaded(self, initialized_config):
        """authorized guilds are loaded into config after on_load"""
        from nova_core.client.events import _do_ready_init

        cfg = initialized_config
        _reset(cfg)

        with _bot_patched(), patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        for guild_id in cfg.authorized_guilds:
            assert guild_id in cfg.guilds or guild_id in cfg.valid_guilds

    async def test_sync_commands_not_called_in_test_mode(self, initialized_config):
        """sync_commands is skipped because test_mode causes early shutdown"""
        from nova_core.client.events import _do_ready_init

        _reset(initialized_config, test_mode=True)

        with _bot_patched() as bot_mocks, patch('nova_core.client.events._shutdown', AsyncMock()):
            await _do_ready_init()

        bot_mocks['sync_commands'].assert_not_called()

    async def test_db_error_triggers_shutdown(self, initialized_config):
        """a database connection error calls _shutdown(exit_code=1)"""
        from nova_core.client.events import _do_ready_init

        _reset(initialized_config)
        mock_shutdown = AsyncMock()

        with (
            _bot_patched(),
            patch('nova_core.database.init_database', new_callable=AsyncMock, side_effect=Exception('db down')),
            patch('nova_core.client.events._shutdown', mock_shutdown),
            patch('attu_logging.webhook.send_to_webhook', new_callable=AsyncMock),
        ):
            await _do_ready_init()

        mock_shutdown.assert_called_once_with(exit_code=1)
