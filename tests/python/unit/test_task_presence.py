# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_task_presence | tests for PresenceUpdateTask."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from nova_core.tasks.presence import PresenceUpdateTask


# --- helpers ---


def _make_task() -> PresenceUpdateTask:
    """return a fresh, unregistered task instance."""
    return PresenceUpdateTask()


# --- on_start ---


class TestOnStart:
    async def test_awaits_config_wait_for_ready(self):
        """on_start delegates to config.wait_for_ready()."""
        task = _make_task()
        mock_cfg = MagicMock()
        mock_cfg.wait_for_ready = AsyncMock()

        with patch('nova_core.tasks.presence.config', mock_cfg):
            await task.on_start()

        mock_cfg.wait_for_ready.assert_awaited_once()


# --- run - happy path ---


class TestRunHappyPath:
    async def test_fetches_count_and_sets_presence(self):
        """run() reads the hatched count and calls bot.change_presence with the right activity."""
        task = _make_task()
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock()

        mock_egg_repo = AsyncMock()
        mock_egg_repo.count_hatched = AsyncMock(return_value=42)

        with (
            patch('nova_core.tasks.presence.bot', mock_bot),
            patch('nova_core.eggs.hatching._egg_repo', mock_egg_repo),
            patch('nova_core.tasks.presence.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_egg_repo.count_hatched.assert_awaited_once()
        mock_bot.change_presence.assert_awaited_once()

        # verify the activity content
        call_kwargs = mock_bot.change_presence.call_args.kwargs
        activity = call_kwargs['activity']
        assert isinstance(activity, discord.Activity)
        assert activity.type == discord.ActivityType.watching
        assert activity.name == '42 eggs hatched'

    async def test_zero_count_sets_presence(self):
        """a zero hatch count still produces a valid presence string."""
        task = _make_task()
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock()

        mock_egg_repo = AsyncMock()
        mock_egg_repo.count_hatched = AsyncMock(return_value=0)

        with (
            patch('nova_core.tasks.presence.bot', mock_bot),
            patch('nova_core.eggs.hatching._egg_repo', mock_egg_repo),
            patch('nova_core.tasks.presence.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        call_kwargs = mock_bot.change_presence.call_args.kwargs
        assert call_kwargs['activity'].name == '0 eggs hatched'


# --- run - egg_repo is None ---


class TestRunRepoNone:
    async def test_returns_early_when_egg_repo_is_none(self):
        """if _egg_repo is None, run() returns immediately without touching bot."""
        task = _make_task()
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock()

        with (
            patch('nova_core.tasks.presence.bot', mock_bot),
            patch('nova_core.eggs.hatching._egg_repo', None),
            patch('nova_core.tasks.presence.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_bot.change_presence.assert_not_awaited()


# --- run - count_hatched raises ---


class TestRunCountError:
    async def test_logs_error_and_returns_early(self):
        """if count_hatched raises, the error is logged and change_presence is not called."""
        task = _make_task()
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock()

        mock_egg_repo = AsyncMock()
        mock_egg_repo.count_hatched = AsyncMock(side_effect=RuntimeError('db timeout'))

        with (
            patch('nova_core.tasks.presence.bot', mock_bot),
            patch('nova_core.eggs.hatching._egg_repo', mock_egg_repo),
            patch('nova_core.tasks.presence.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_logger.error.assert_called_once()
        assert 'failed to count hatched eggs' in str(mock_logger.error.call_args)
        mock_bot.change_presence.assert_not_awaited()


# --- run - change_presence raises ---


class TestRunPresenceError:
    async def test_logs_error_when_change_presence_fails(self):
        """if change_presence raises, the error is logged."""
        task = _make_task()
        mock_bot = MagicMock()
        mock_bot.change_presence = AsyncMock(side_effect=RuntimeError('gateway error'))

        mock_egg_repo = AsyncMock()
        mock_egg_repo.count_hatched = AsyncMock(return_value=10)

        with (
            patch('nova_core.tasks.presence.bot', mock_bot),
            patch('nova_core.eggs.hatching._egg_repo', mock_egg_repo),
            patch('nova_core.tasks.presence.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_logger.error.assert_called_once()
        assert 'failed to update presence' in str(mock_logger.error.call_args)


# --- singleton and metadata ---


class TestSingleton:
    def test_module_level_singleton_exists(self):
        """the module exposes a presence_update_task singleton instance."""
        from nova_core.tasks.presence import presence_update_task

        assert isinstance(presence_update_task, PresenceUpdateTask)
        assert presence_update_task.name == 'PresenceUpdate'

    def test_task_metadata(self):
        """verify task name, interval, and default flags."""
        task = _make_task()
        assert task.name == 'PresenceUpdate'
        assert task.interval == timedelta(minutes=30)
        assert task.run_immediately is True
        assert task.run_once is False
