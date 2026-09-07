# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_task_error_hook | tests for ErrorHookTask."""

from unittest.mock import AsyncMock, MagicMock, patch

from nova_core.tasks.error_hook import ErrorHookTask, error_hook_refresh


# --- helpers ---


def _make_task() -> ErrorHookTask:
    """return a fresh, unregistered task instance."""
    return ErrorHookTask()


def _make_bot(**overrides):
    """return a mock bot with sensible defaults."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.user = MagicMock()
    bot.user.name = 'DoomBot'
    bot.user.id = 1111111111

    guild = MagicMock()
    channel = MagicMock()
    channel.webhooks = AsyncMock(return_value=[])
    channel.create_webhook = AsyncMock()
    guild.get_channel = MagicMock(return_value=channel)
    bot.get_guild = MagicMock(return_value=guild)

    for key, val in overrides.items():
        setattr(bot, key, val)

    return bot


def _make_config(**overrides):
    """return a mock config with sensible defaults."""
    cfg = MagicMock()
    cfg.wait_for_load = AsyncMock()
    cfg.test_mode = False
    cfg.error_log = (123456, 789012)
    cfg.error_hook = 'https://discord.com/api/webhooks/old-hook'
    cfg.config_repo = MagicMock()
    cfg.config_repo.update_system_field = AsyncMock()

    for key, val in overrides.items():
        setattr(cfg, key, val)

    return cfg


def _make_webhook(url, user=None):
    """return a mock webhook object."""
    hook = MagicMock()
    hook.url = url
    hook.name = 'DoomBot'
    hook.id = 999
    hook.user = user
    hook.delete = AsyncMock()
    return hook


# --- on_start ---


class TestOnStart:
    async def test_awaits_config_ready_and_bot_ready(self):
        task = _make_task()
        mock_cfg = _make_config()
        mock_bot = _make_bot()

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot):
            await task.on_start()

        mock_cfg.wait_for_load.assert_awaited_once()
        mock_bot.wait_until_ready.assert_awaited_once()


# --- run - test mode ---


class TestRunTestMode:
    async def test_skips_when_test_mode(self):
        """in test mode, run() returns immediately without touching webhooks."""
        task = _make_task()
        mock_cfg = _make_config(test_mode=True)
        mock_bot = _make_bot()

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_bot.get_guild.assert_not_called()


# --- run - happy path (webhook already valid) ---


class TestRunHappyPath:
    async def test_existing_webhook_skips_creation(self):
        """when config.error_hook is already in the channel's webhook list, no new webhook is created."""
        task = _make_task()
        existing_url = 'https://discord.com/api/webhooks/good-hook'
        mock_cfg = _make_config(error_hook=existing_url)
        mock_bot = _make_bot()

        existing_webhook = _make_webhook(existing_url, user=mock_bot.user)
        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[existing_webhook])

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        channel.create_webhook.assert_not_awaited()


# --- run - webhook missing, creates new one ---


class TestRunWebhookMissing:
    async def test_creates_webhook_when_url_not_in_list(self):
        """when error_hook url is not in channel webhooks, a new webhook is created."""
        task = _make_task()
        mock_cfg = _make_config(error_hook='https://discord.com/api/webhooks/stale')
        mock_bot = _make_bot()

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[])
        new_hook = MagicMock()
        new_hook.name = 'DoomBot'
        new_hook.id = 12345
        new_hook.url = 'https://discord.com/api/webhooks/new-hook'
        channel.create_webhook = AsyncMock(return_value=new_hook)

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        channel.create_webhook.assert_awaited_once()
        # config should be updated with the new url
        assert mock_cfg.error_hook == new_hook.url
        mock_cfg.config_repo.update_system_field.assert_awaited_once_with('error_hook', new_hook.url)


# --- run - avatar generation ---


class TestRunWebhookCreationWithAvatar:
    async def test_generate_png_called_with_correct_args(self):
        """generate_png is called with rotation=45 and color='#ff4941' for the webhook icon."""
        task = _make_task()
        mock_cfg = _make_config(error_hook='https://discord.com/api/webhooks/missing')
        mock_bot = _make_bot()

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[])
        new_hook = MagicMock()
        new_hook.name = 'DoomBot'
        new_hook.id = 55555
        new_hook.url = 'https://discord.com/api/webhooks/fresh'
        channel.create_webhook = AsyncMock(return_value=new_hook)

        icon_bytes = b'\x89PNG-icon-data'

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.generate_png', new_callable=AsyncMock, return_value=icon_bytes) as mock_png, patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_png.assert_awaited_once_with(45, '#ff4941')
        # verify the icon bytes were passed to create_webhook
        call_kwargs = channel.create_webhook.call_args
        assert call_kwargs.kwargs.get('avatar') == icon_bytes or call_kwargs[1].get('avatar') == icon_bytes


# --- run - old webhook cleanup ---


class TestRunOldWebhookCleanup:
    async def test_deletes_old_webhooks_owned_by_bot(self):
        """webhooks owned by the bot with a different url than config.error_hook are deleted."""
        task = _make_task()
        current_url = 'https://discord.com/api/webhooks/current'
        mock_cfg = _make_config(error_hook=current_url)
        mock_bot = _make_bot()

        old_webhook = _make_webhook('https://discord.com/api/webhooks/old', user=mock_bot.user)
        current_webhook = _make_webhook(current_url, user=mock_bot.user)

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[old_webhook, current_webhook])

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        old_webhook.delete.assert_awaited_once()
        current_webhook.delete.assert_not_awaited()

    async def test_does_not_delete_webhooks_from_other_users(self):
        """webhooks created by other users are not deleted, even if their url differs."""
        task = _make_task()
        current_url = 'https://discord.com/api/webhooks/current'
        mock_cfg = _make_config(error_hook=current_url)
        mock_bot = _make_bot()

        other_user = MagicMock()
        other_user.id = 9999999
        other_webhook = _make_webhook('https://discord.com/api/webhooks/other', user=other_user)
        current_webhook = _make_webhook(current_url, user=mock_bot.user)

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[other_webhook, current_webhook])

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        other_webhook.delete.assert_not_awaited()


class TestRunOldWebhookCleanupFails:
    async def test_logs_warning_when_delete_fails(self):
        """if deleting an old webhook raises, a warning is logged but execution continues."""
        task = _make_task()
        current_url = 'https://discord.com/api/webhooks/current'
        mock_cfg = _make_config(error_hook=current_url)
        mock_bot = _make_bot()

        old_webhook = _make_webhook('https://discord.com/api/webhooks/old', user=mock_bot.user)
        old_webhook.delete = AsyncMock(side_effect=Exception('forbidden'))
        current_webhook = _make_webhook(current_url, user=mock_bot.user)

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[old_webhook, current_webhook])

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        # a warning should be logged about the deletion failure
        mock_logger.warning.assert_called_once()
        assert 'failed to delete' in mock_logger.warning.call_args[0][0]


# --- run - discord api error during creation ---


class TestRunDiscordApiError:
    async def test_logs_error_when_create_webhook_fails(self):
        """if create_webhook raises, an error is logged and config is not updated."""
        task = _make_task()
        mock_cfg = _make_config(error_hook='https://discord.com/api/webhooks/gone')
        mock_bot = _make_bot()

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[])
        channel.create_webhook = AsyncMock(side_effect=Exception('rate limited'))

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_logger.exception.assert_called_once()
        assert 'failed to create' in mock_logger.exception.call_args[0][0]
        # config should remain unchanged
        mock_cfg.config_repo.update_system_field.assert_not_awaited()


# --- run - outer exception (guild/channel lookup fails) ---


class TestRunOuterException:
    async def test_logs_error_when_guild_lookup_fails(self):
        """if bot.get_guild or guild.get_channel raises, the outer except catches it."""
        task = _make_task()
        mock_cfg = _make_config()
        mock_bot = _make_bot()
        mock_bot.get_guild = MagicMock(side_effect=Exception('guild not found'))

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_logger.exception.assert_called_once()
        assert 'failed acquiring' in mock_logger.exception.call_args[0][0]


# --- run - config persistence after webhook update ---


class TestRunConfigPersistence:
    async def test_updates_config_after_new_webhook(self):
        """after creating a new webhook, config.error_hook is set and config_repo.update_system_field is called."""
        task = _make_task()
        mock_cfg = _make_config(error_hook='https://discord.com/api/webhooks/expired')
        mock_bot = _make_bot()

        channel = mock_bot.get_guild.return_value.get_channel.return_value
        channel.webhooks = AsyncMock(return_value=[])
        new_hook = MagicMock()
        new_hook.name = 'DoomBot'
        new_hook.id = 77777
        new_hook.url = 'https://discord.com/api/webhooks/persisted'
        channel.create_webhook = AsyncMock(return_value=new_hook)

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert mock_cfg.error_hook == 'https://discord.com/api/webhooks/persisted'
        mock_cfg.config_repo.update_system_field.assert_awaited_once_with('error_hook', 'https://discord.com/api/webhooks/persisted')


# --- standalone function ---


class TestStandaloneFunction:
    async def test_error_hook_refresh_calls_run(self):
        """the standalone error_hook_refresh() creates a task and runs it."""
        mock_cfg = _make_config(test_mode=True)
        mock_bot = _make_bot()

        with patch('nova_core.tasks.error_hook.config', mock_cfg), patch('nova_core.tasks.error_hook.bot', mock_bot), patch('nova_core.tasks.error_hook.logger') as mock_logger:
            mock_logger.send_to_webhook = AsyncMock()
            await error_hook_refresh()

        # in test mode it returns early - verifying it ran without error is sufficient


# --- singleton ---


class TestSingleton:
    def test_module_level_singleton_exists(self):
        """the module exposes an error_hook_task singleton instance."""
        from nova_core.tasks.error_hook import error_hook_task

        assert isinstance(error_hook_task, ErrorHookTask)
        assert error_hook_task.name == 'ErrorHookRefresh'

    def test_task_metadata(self):
        """verify task name, interval, and run_immediately are set correctly."""
        task = _make_task()
        assert task.name == 'ErrorHookRefresh'
        assert task.interval.total_seconds() == 3600
        assert task.run_immediately is True
