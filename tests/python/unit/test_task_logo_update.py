"""
AttuBot - Tests for LogoUpdateTask
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import colorsys
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from nova_core.tasks.logo_update import LogoUpdateTask


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_task() -> LogoUpdateTask:
    """return a fresh, unregistered task instance."""
    return LogoUpdateTask()


def _make_theme(**overrides):
    """return a mock theme object with sensible defaults."""
    theme = MagicMock()
    theme.rotation = 90.0
    theme.max_rate = 0.5
    theme.bot_color = '#ff0000'
    theme.guild_color = '#ffffff'
    theme.logo_rings = '#000000'
    theme.logo_planet = '#000000'
    theme.saturation = 1.0
    theme.lightness = 0.5
    theme.save = AsyncMock()

    for key, val in overrides.items():
        setattr(theme, key, val)

    return theme


def _make_epoch(paused=False):
    """return a mock epoch object."""
    epoch = MagicMock()
    epoch.paused = paused
    return epoch


def _make_guild_config(epoch=None, role_id=0):
    """return a mock guild config."""
    gc = MagicMock()
    gc.epoch = epoch or _make_epoch()
    gc.roles = MagicMock()
    gc.roles.bot_color = role_id
    return gc


def _make_config(theme=None, guild_config=None, **overrides):
    """return a mock config with sensible defaults."""
    cfg = MagicMock()
    cfg.wait_for_load = AsyncMock()
    cfg.theme = theme or _make_theme()
    gc = guild_config or _make_guild_config()
    cfg.primary = MagicMock(return_value=gc)
    cfg.get_guild_by_role.return_value.id = 123456

    for key, val in overrides.items():
        setattr(cfg, key, val)

    return cfg


def _make_bot():
    """return a mock bot with sensible defaults."""
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    bot.user = MagicMock()
    bot.user.edit = AsyncMock()

    guild = MagicMock()
    guild.name = 'Test Server'
    guild.edit = AsyncMock()
    guild.emojis = []
    guild.create_custom_emoji = AsyncMock()
    guild.get_role = MagicMock(return_value=None)
    bot.get_guild = MagicMock(return_value=guild)
    bot.fetch_guild = AsyncMock(return_value=guild)

    return bot


def _make_year_span(start_time=1700000000, duration=14):
    """return a mock AttuYearSpan."""
    span = MagicMock()
    span.start_time = start_time
    span.end_time = start_time + (duration * 86400)
    span.duration = duration
    return span


# ---------------------------------------------------------------------------
# on_start
# ---------------------------------------------------------------------------


class TestOnStart:
    async def test_awaits_config_and_bot_then_sleeps(self):
        """on_start waits for config, bot, then sleeps 10 minutes."""
        task = _make_task()
        mock_cfg = _make_config()
        mock_bot = _make_bot()

        with patch('nova_core.tasks.logo_update.config', mock_cfg), patch('nova_core.tasks.logo_update.bot', mock_bot), patch('nova_core.tasks.logo_update.asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            await task.on_start()

        mock_cfg.wait_for_load.assert_awaited_once()
        mock_bot.wait_until_ready.assert_awaited_once()
        mock_sleep.assert_awaited_once_with(10 * 60)


# ---------------------------------------------------------------------------
# run — happy path (epoch not paused)
# ---------------------------------------------------------------------------


class TestRunHappyPath:
    async def test_calculates_rotation_and_updates_avatar(self):
        """when epoch is not paused, rotation is calculated from elapsed time and icons are updated."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=False), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        year_span = _make_year_span(start_time=int((datetime.now().astimezone() - timedelta(days=7)).timestamp()), duration=14)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.get_year_status', return_value=(100, 5)),
            patch('nova_core.tasks.logo_update.get_year_span', new_callable=AsyncMock, return_value=year_span),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG') as mock_png,
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        # generate_png called twice (bot avatar and guild icon)
        assert mock_png.call_count == 2
        # guild.edit and bot.user.edit should be called
        guild = mock_bot.get_guild.return_value
        guild.edit.assert_awaited_once()
        mock_bot.user.edit.assert_awaited_once()
        # theme should be saved
        theme.save.assert_awaited_once()

    async def test_rotation_stored_modulo_360(self):
        """the stored rotation is always mod 360."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=False), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        # set up so that rotation will be > 360 (start_time far in the past)
        start_ts = int((datetime.now().astimezone() - timedelta(days=30)).timestamp())
        year_span = _make_year_span(start_time=start_ts, duration=14)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.get_year_status', return_value=(100, 5)),
            patch('nova_core.tasks.logo_update.get_year_span', new_callable=AsyncMock, return_value=year_span),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert 0 <= theme.rotation < 360


# ---------------------------------------------------------------------------
# run — epoch paused
# ---------------------------------------------------------------------------


class TestRunEpochPaused:
    async def test_uses_random_drift_when_paused(self):
        """when epoch is paused, rotation is incremented by a random amount based on max_rate."""
        task = _make_task()
        theme = _make_theme(rotation=100.0, max_rate=0.5)
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.8),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        # new_rotation = 100.0 + (0.8 * 0.5) = 100.4
        # stored as 100.4 % 360 = 100.4
        assert theme.rotation == 100.4
        theme.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# color math
# ---------------------------------------------------------------------------


class TestColorMath:
    def test_hsl_to_hex_red(self):
        """hue=0, saturation=1.0, lightness=0.5 produces pure red."""
        hue = 0.0 / 360.0  # 0 degrees
        r, g, b = colorsys.hls_to_rgb(hue, 0.5, 1.0)
        computed = f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'
        assert computed == '#ff0000'

    def test_hsl_to_hex_green(self):
        """hue=120, saturation=1.0, lightness=0.5 produces pure green."""
        hue = 120.0 / 360.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.5, 1.0)
        computed = f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'
        assert computed == '#00ff00'

    def test_hsl_to_hex_blue(self):
        """hue=240, saturation=1.0, lightness=0.5 produces pure blue."""
        hue = 240.0 / 360.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.5, 1.0)
        computed = f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'
        assert computed == '#0000ff'

    def test_hsl_to_hex_with_custom_lightness(self):
        """reduced lightness produces a darker color."""
        hue = 0.0 / 360.0
        r, g, b = colorsys.hls_to_rgb(hue, 0.25, 1.0)
        computed = f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'
        # at lightness=0.25, saturation=1.0, hue=0: red channel should be 128 (0x80), others 0
        assert computed == '#800000'

    async def test_computed_color_matches_expected_for_known_rotation(self):
        """verify the full color pipeline: rotation -> hue -> hls_to_rgb -> hex."""
        task = _make_task()
        # rotation=0 means hue=0 -> pure red at s=1, l=0.5
        theme = _make_theme(rotation=50.0, saturation=1.0, lightness=0.5)
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        # force random() to return 0 so new_rotation = 50.0 + 0 = 50.0
        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG') as mock_png,
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        # rotation=50 -> hue=50/360 -> hls_to_rgb(0.1389, 0.5, 1.0)
        expected_hue = (50.0 % 360) / 360.0
        er, eg, eb = colorsys.hls_to_rgb(expected_hue, 0.5, 1.0)
        expected_color = f'#{round(er * 255):02x}{round(eg * 255):02x}{round(eb * 255):02x}'

        assert theme.bot_color == expected_color
        # the first generate_png call (bot avatar) should use computed_color
        first_call_args = mock_png.call_args_list[0]
        assert first_call_args[0][1] == expected_color


# ---------------------------------------------------------------------------
# run — guild avatar, emoji, and role updates
# ---------------------------------------------------------------------------


class TestRunGuildAvatarUpdate:
    async def test_guild_edit_called_with_icon(self):
        """guild.edit is called with the guild icon bytes."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value

        guild_icon_bytes = b'\x89PNG-guild'
        bot_avatar_bytes = b'\x89PNG-bot'
        call_count = 0

        async def fake_generate_png(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return bot_avatar_bytes if call_count == 1 else guild_icon_bytes

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', side_effect=fake_generate_png),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        guild.edit.assert_awaited_once()
        call_kwargs = guild.edit.call_args
        assert call_kwargs.kwargs.get('icon') == guild_icon_bytes
        assert call_kwargs.kwargs.get('reason') == 'logo update task'


class TestRunBotAvatarUpdate:
    async def test_bot_user_edit_called_with_avatar(self):
        """bot.user.edit is called with the bot avatar bytes."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_bot.user.edit.assert_awaited_once()
        call_kwargs = mock_bot.user.edit.call_args
        assert call_kwargs.kwargs.get('avatar') == b'\x89PNG'


class TestRunEmojiUpdate:
    async def test_old_emoji_deleted_and_new_created(self):
        """matching emojis are deleted before creating the new one."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value
        guild.name = 'Test Server'

        # the emoji name is guild.name.replace(' ', '_').lower() = 'test_server'
        old_emoji = MagicMock()
        old_emoji.name = 'test_server'
        old_emoji.delete = AsyncMock()
        guild.emojis = [old_emoji]

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        old_emoji.delete.assert_awaited_once()
        guild.create_custom_emoji.assert_awaited_once()
        create_kwargs = guild.create_custom_emoji.call_args.kwargs
        assert create_kwargs['name'] == 'test_server'
        assert create_kwargs['reason'] == 'logo update task'

    async def test_no_matching_emoji_still_creates_new(self):
        """when no existing emoji matches, create_custom_emoji is still called."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value
        guild.name = 'Test Server'
        guild.emojis = []  # no existing emojis

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        guild.create_custom_emoji.assert_awaited_once()


class TestRunRoleColorUpdate:
    async def test_role_edit_called_with_correct_color(self):
        """when a bot_color role is configured, role.edit is called with the computed discord.Color."""
        task = _make_task()
        theme = _make_theme(saturation=1.0, lightness=0.5)
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=999888)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value

        mock_role = MagicMock()
        mock_role.name = 'BotColor'
        mock_role.edit = AsyncMock()
        guild.get_role = MagicMock(return_value=mock_role)

        # force rotation to 0 -> hue=0 -> red
        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_role.edit.assert_awaited_once()
        call_kwargs = mock_role.edit.call_args.kwargs
        assert isinstance(call_kwargs['color'], discord.Color)
        assert call_kwargs['reason'] == 'logo update task'


# ---------------------------------------------------------------------------
# run — error handling
# ---------------------------------------------------------------------------


class TestRunGuildEditFails:
    async def test_logs_error_and_continues_to_bot_edit(self):
        """if guild.edit raises, it is logged and bot.user.edit is still attempted."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value
        guild.edit = AsyncMock(side_effect=Exception('forbidden'))

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        # guild error logged
        assert any('failed to update guild icon' in str(c) for c in mock_logger.error.call_args_list)
        # bot avatar update still attempted
        mock_bot.user.edit.assert_awaited_once()
        # theme still saved
        theme.save.assert_awaited_once()


class TestRunBotEditFails:
    async def test_logs_error_and_continues_to_emoji_update(self):
        """if bot.user.edit raises, it is logged and emoji update still proceeds."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        mock_bot.user.edit = AsyncMock(side_effect=Exception('rate limited'))
        guild = mock_bot.get_guild.return_value

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert any('failed to update bot avatar' in str(c) for c in mock_logger.error.call_args_list)
        # emoji creation still attempted
        guild.create_custom_emoji.assert_awaited_once()
        theme.save.assert_awaited_once()


class TestRunEmojiUpdateFails:
    async def test_logs_error_and_continues_to_role_update(self):
        """if emoji operations raise, the error is logged and role update still proceeds."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=777)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value
        guild.create_custom_emoji = AsyncMock(side_effect=Exception('emoji limit'))

        mock_role = MagicMock()
        mock_role.name = 'BotColor'
        mock_role.edit = AsyncMock()
        guild.get_role = MagicMock(return_value=mock_role)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert any('failed to update guild emoji' in str(c) for c in mock_logger.error.call_args_list)
        mock_role.edit.assert_awaited_once()
        theme.save.assert_awaited_once()


class TestRunRoleUpdateFails:
    async def test_logs_error_and_continues_to_save(self):
        """if role.edit raises, the error is logged and theme.save still happens."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=777)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value

        mock_role = MagicMock()
        mock_role.name = 'BotColor'
        mock_role.edit = AsyncMock(side_effect=Exception('missing permissions'))
        guild.get_role = MagicMock(return_value=mock_role)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert any('failed to update bot_color role' in str(c) for c in mock_logger.error.call_args_list)
        theme.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# run — no role configured
# ---------------------------------------------------------------------------


class TestRunNoRoleId:
    async def test_skips_role_update_when_role_id_is_zero(self):
        """when roles.bot_color is 0, role.edit is never called."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        guild.get_role.assert_not_called()

    async def test_skips_role_update_when_role_not_found(self):
        """when guild.get_role returns None, role.edit is never called."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=999)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()
        guild = mock_bot.get_guild.return_value
        guild.get_role = MagicMock(return_value=None)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        guild.get_role.assert_called_once_with(999)
        # no role.edit should be attempted since get_role returned None
        theme.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# run — theme persistence
# ---------------------------------------------------------------------------


class TestRunThemePersistence:
    async def test_theme_rotation_and_color_saved(self):
        """after a successful run, theme.rotation and theme.bot_color are updated and save() is called."""
        task = _make_task()
        theme = _make_theme(rotation=200.0, saturation=1.0, lightness=0.5)
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        # random()=0.5 -> new_rotation = 200.0 + (0.5 * 0.5) = 200.25
        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.5),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        assert theme.rotation == 200.25
        # verify bot_color was computed from the new rotation
        expected_hue = (200.25 % 360) / 360.0
        er, eg, eb = colorsys.hls_to_rgb(expected_hue, 0.5, 1.0)
        expected_color = f'#{round(er * 255):02x}{round(eg * 255):02x}{round(eb * 255):02x}'
        assert theme.bot_color == expected_color
        theme.save.assert_awaited_once()


# ---------------------------------------------------------------------------
# run — guild fetched via fetch_guild fallback
# ---------------------------------------------------------------------------


class TestRunGuildFetchFallback:
    async def test_fetches_guild_when_get_guild_returns_none(self):
        """when bot.get_guild returns None, bot.fetch_guild is used as fallback."""
        task = _make_task()
        theme = _make_theme()
        gc = _make_guild_config(epoch=_make_epoch(paused=True), role_id=0)
        mock_cfg = _make_config(theme=theme, guild_config=gc)
        mock_bot = _make_bot()

        fallback_guild = MagicMock()
        fallback_guild.name = 'Fallback Server'
        fallback_guild.edit = AsyncMock()
        fallback_guild.emojis = []
        fallback_guild.create_custom_emoji = AsyncMock()
        fallback_guild.get_role = MagicMock(return_value=None)

        mock_bot.get_guild = MagicMock(return_value=None)
        mock_bot.fetch_guild = AsyncMock(return_value=fallback_guild)

        with (
            patch('nova_core.tasks.logo_update.config', mock_cfg),
            patch('nova_core.tasks.logo_update.bot', mock_bot),
            patch('nova_core.tasks.logo_update.random', return_value=0.0),
            patch('nova_core.tasks.logo_update.generate_png', new_callable=AsyncMock, return_value=b'\x89PNG'),
            patch('nova_core.tasks.logo_update.logger') as mock_logger,
        ):
            mock_logger.send_to_webhook = AsyncMock()
            await task.run()

        mock_bot.fetch_guild.assert_awaited_once_with(123456)
        fallback_guild.edit.assert_awaited_once()


# ---------------------------------------------------------------------------
# singleton and metadata
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_module_level_singleton_exists(self):
        """the module exposes a logo_update_task singleton instance."""
        from nova_core.tasks.logo_update import logo_update_task

        assert isinstance(logo_update_task, LogoUpdateTask)
        assert logo_update_task.name == 'LogoUpdateEvent'

    def test_task_metadata(self):
        """verify task name, interval, and default flags."""
        task = _make_task()
        assert task.name == 'LogoUpdateEvent'
        assert task.interval.total_seconds() == 600
        assert task.run_immediately is False
        assert task.run_once is False
