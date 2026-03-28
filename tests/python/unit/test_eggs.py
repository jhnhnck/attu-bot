"""
AttuBot - Egg Game Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for the egg collection game. All tests mock Discord, repo, and asyncio
dependencies - no real DB or network calls.
"""

import time
from datetime import date
from unittest.mock import AsyncMock, MagicMock, call, patch

import discord
import pytest

import attubot.eggs.hatching as hatching_mod
from attubot.database.models import EggDocument, EggUserDocument
from attubot.eggs.hatching import (
    _egg_emoji_str,
    collect_egg,
    ensure_eggs_ready,
    hatch_date,
    hatch_egg,
    run_hatch_animation,
)
from attubot.tasks.scheduler import scheduler as real_scheduler


# ---- constants ----

test_guild = 1234567890
test_user = 9876543210
test_user2 = 1111111111
test_thread = 5555555555
test_message = 222222222222


# ---- helpers ----


def _make_egg(*, hatched=False, hatches_at=0.0, message_id=test_message, rarity='common', result='🐣'):
    return EggDocument(
        egg_id='test-egg-id',
        guild_id=test_guild,
        user_id=test_user,
        rarity=rarity,
        collected_at=1000.0,
        hatches_at=hatches_at,
        hatched=hatched,
        result=result,
        message_id=message_id,
    )


def _make_user_doc(*, thread_id=test_thread, last_collected_at=0.0):
    return EggUserDocument(
        guild_id=test_guild,
        user_id=test_user,
        thread_id=thread_id,
        last_collected_at=last_collected_at,
    )


# ============================================================
# hatch_date()
# ============================================================


class TestHatchDate:
    def test_returns_date_type(self):
        result = hatch_date(2026)
        assert isinstance(result, date)

    def test_known_years(self):
        assert hatch_date(2024) == date(2024, 3, 31)
        assert hatch_date(2025) == date(2025, 4, 20)
        assert hatch_date(2026) == date(2026, 4, 5)
        assert hatch_date(2019) == date(2019, 4, 21)


# ============================================================
# collect_egg()
# ============================================================


class TestCollectEgg:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        """patch module-level repo singletons and bot.get_channel"""
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()

        # mock user egg thread (returned by create_thread)
        mock_thread = MagicMock()
        mock_msg = MagicMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.send = AsyncMock(return_value=mock_msg)
        mock_thread.id = test_thread

        # mock the eggs channel (bot.get_channel returns this; also serves as thread in existing-user path)
        mock_eggs_channel = MagicMock()
        mock_eggs_channel.create_thread = AsyncMock(return_value=mock_thread)
        mock_eggs_channel.send = AsyncMock(return_value=mock_msg)

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('attubot.eggs.hatching.bot') as mock_bot,
        ):
            mock_bot.get_channel.return_value = mock_eggs_channel
            mock_bot.get_guild.return_value = MagicMock()
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.thread = mock_thread
            self.eggs_channel = mock_eggs_channel
            yield

    async def test_new_user_succeeds(self):
        """new user with no prior doc - should insert egg and upsert user"""
        self.egg_user_repo.get.return_value = None
        self.egg_user_repo.upsert.return_value = None
        self.egg_repo.insert.return_value = None

        # supply a guild config with a valid eggs channel
        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = test_thread

        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg

            result = await collect_egg(test_guild, test_user, 'testuser')

        assert isinstance(result, str)
        assert 'discord.com' in result
        self.egg_repo.insert.assert_called_once()
        # upsert called twice for new user: once in get_or_create_user_thread, once to update cooldown
        assert self.egg_user_repo.upsert.call_count == 2

    async def test_cooldown_active_raises(self):
        """user collected 60s ago - still within 900s cooldown"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=time.time() - 60)

        with pytest.raises(ValueError, match='try again in'):
            await collect_egg(test_guild, test_user, 'testuser')

    async def test_cooldown_expired_succeeds(self):
        """user collected 1000s ago - cooldown has elapsed"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=time.time() - 1000)
        self.egg_user_repo.upsert.return_value = None
        self.egg_repo.insert.return_value = None

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = test_thread

        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg

            result = await collect_egg(test_guild, test_user, 'testuser')

        assert isinstance(result, str)
        self.egg_repo.insert.assert_called_once()


# ============================================================
# hatch_egg()
# ============================================================


class TestHatchEgg:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch.object(real_scheduler, 'add_job') as mock_add_job,
        ):
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_add_job = mock_add_job
            yield

    async def test_no_eggs(self):
        self.egg_repo.get_oldest_ready.return_value = None
        self.egg_repo.get_next_unhatched.return_value = None

        result, ts = await hatch_egg(test_guild, test_user)

        assert result == 'no_eggs'
        assert ts is None

    async def test_egg_not_ready(self):
        self.egg_repo.get_oldest_ready.return_value = None
        next_egg = _make_egg(hatches_at=9999.0)
        self.egg_repo.get_next_unhatched.return_value = next_egg

        result, ts = await hatch_egg(test_guild, test_user)

        assert result == ''
        assert ts == 9999.0

    async def test_egg_ready(self):
        egg = _make_egg(hatches_at=100.0, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        self.egg_repo.mark_hatched.return_value = None

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_msg = AsyncMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.fetch_message = AsyncMock(return_value=mock_msg)
        self.mock_bot.get_channel.return_value = mock_thread

        result, ts = await hatch_egg(test_guild, test_user)

        assert 'discord.com' in result
        assert ts is None
        self.egg_repo.mark_hatched.assert_called_once_with(egg.egg_id, egg.result)
        self.mock_add_job.assert_called_once()


# ============================================================
# run_hatch_animation()
# ============================================================


class TestRunHatchAnimation:
    async def test_animation_sequence(self):
        """verify the three-stage edit sequence and sleep durations"""
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()

        sleep_calls = []

        async def fake_sleep(t):
            sleep_calls.append(t)

        with patch('attubot.eggs.hatching.asyncio') as mock_asyncio:
            mock_asyncio.sleep = AsyncMock(side_effect=fake_sleep)

            await run_hatch_animation(mock_message, '🐣', 'common')

        # first sleep must be 10-15 seconds
        assert len(sleep_calls) == 2
        assert 10 <= sleep_calls[0] <= 15
        assert sleep_calls[1] == 1

        # verify edit sequence: first call to 💢, second call to result
        edit_calls = mock_message.edit.call_args_list
        assert len(edit_calls) == 2
        assert edit_calls[0] == call(content='💢')
        assert edit_calls[1] == call(content='🐣')


# ============================================================
# ensure_eggs_ready()
# ============================================================


class TestEnsureEggsReady:
    async def test_creates_channel_when_missing(self):
        """channels.eggs == 0 - should create channel and persist ID"""
        mock_channel = AsyncMock()
        mock_channel.id = 777888999
        mock_channel.send = AsyncMock()

        mock_discord_guild = MagicMock()
        mock_discord_guild.create_text_channel = AsyncMock(return_value=mock_channel)
        mock_discord_guild.get_channel.return_value = MagicMock(category=None)

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.id = test_guild
        mock_guild_cfg.channels.eggs = 0
        mock_guild_cfg.channels.general = 0

        mock_config_repo = AsyncMock()

        with (
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch('attubot.eggs.hatching.config') as mock_config,
        ):
            mock_bot.get_guild.return_value = mock_discord_guild
            mock_config.primary.return_value = mock_guild_cfg
            mock_config.config_repo = mock_config_repo

            await ensure_eggs_ready()

        mock_discord_guild.create_text_channel.assert_called_once_with('eggs', category=None)
        mock_config_repo.update_guild_field.assert_called_once_with(test_guild, 'channels.eggs', mock_channel.id)

    async def test_skips_if_channel_exists(self):
        """channels.eggs already set - should not create another channel"""
        mock_discord_guild = MagicMock()
        mock_discord_guild.create_text_channel = AsyncMock()

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.id = test_guild
        mock_guild_cfg.channels.eggs = 12345

        with (
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch('attubot.eggs.hatching.config') as mock_config,
        ):
            mock_bot.get_guild.return_value = mock_discord_guild
            mock_config.primary.return_value = mock_guild_cfg

            await ensure_eggs_ready()

        mock_discord_guild.create_text_channel.assert_not_called()


# ============================================================
# _egg_emoji_str()
# ============================================================


class TestEggEmojiStr:
    def test_with_emoji_id_returns_formatted(self):
        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.theme.egg_emojis.get.return_value = 123456789
            result = _egg_emoji_str('common')
        assert result == '<:common_egg:123456789>'

    def test_without_emoji_id_returns_fallback(self):
        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.theme.egg_emojis.get.return_value = None
            result = _egg_emoji_str('common')
        assert result == ':common_egg:'


# ============================================================
# get_or_create_user_thread() - cache miss paths
# ============================================================


class TestGetOrCreateUserThread:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_user_repo = AsyncMock()
        with (
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch('attubot.eggs.hatching.config') as mock_config,
        ):
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_config = mock_config
            yield

    async def test_thread_cache_miss_fetches_from_api(self):
        """thread in user_doc but not in bot cache - fetches via guild api"""
        from attubot.eggs.hatching import get_or_create_user_thread

        user_doc = _make_user_doc(thread_id=test_thread)
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        self.mock_bot.get_channel.return_value = None
        mock_guild = MagicMock()
        mock_guild.fetch_channel = AsyncMock(return_value=mock_thread)
        self.mock_bot.get_guild.return_value = mock_guild

        result = await get_or_create_user_thread(test_guild, test_user, 'testuser')

        assert result is mock_thread
        mock_guild.fetch_channel.assert_called_once_with(test_thread)

    async def test_thread_deleted_falls_through_to_recreate(self):
        """fetch_channel raises NotFound - falls through and creates a new thread"""
        from attubot.eggs.hatching import get_or_create_user_thread

        user_doc = _make_user_doc(thread_id=test_thread)
        self.egg_user_repo.get.return_value = user_doc

        mock_new_thread = MagicMock()
        mock_new_thread.id = 8888888888
        mock_eggs_channel = MagicMock()
        mock_eggs_channel.create_thread = AsyncMock(return_value=mock_new_thread)

        mock_guild = MagicMock()
        mock_guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
        self.mock_bot.get_guild.return_value = mock_guild

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = 4444444444
        self.mock_config.guild.return_value = mock_guild_cfg

        # first call (thread lookup) returns None; second (eggs channel lookup) returns the channel
        self.mock_bot.get_channel.side_effect = [None, mock_eggs_channel]

        result = await get_or_create_user_thread(test_guild, test_user, 'testuser')

        assert result is mock_new_thread
        self.egg_user_repo.upsert.assert_called_once()


# ============================================================
# hatch_egg() - additional cache-miss and guard paths
# ============================================================


class TestHatchEggCacheMiss:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch.object(real_scheduler, 'add_job') as mock_add_job,
        ):
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_add_job = mock_add_job
            yield

    async def test_thread_cache_miss_fetches_from_guild(self):
        """thread not in bot cache - should fetch via guild api"""
        egg = _make_egg(hatches_at=100.0, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        self.egg_repo.mark_hatched.return_value = None

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_msg = AsyncMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.fetch_message = AsyncMock(return_value=mock_msg)

        mock_guild = MagicMock()
        mock_guild.fetch_channel = AsyncMock(return_value=mock_thread)

        self.mock_bot.get_channel.return_value = None
        self.mock_bot.get_guild.return_value = mock_guild

        result, _ = await hatch_egg(test_guild, test_user)

        assert 'discord.com' in result
        mock_guild.fetch_channel.assert_called_once_with(test_thread)

    async def test_guild_cache_miss_raises(self):
        """both thread and guild not in cache - should raise"""
        egg = _make_egg(hatches_at=100.0, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        self.mock_bot.get_channel.return_value = None
        self.mock_bot.get_guild.return_value = None

        with pytest.raises(RuntimeError, match='not in cache'):
            await hatch_egg(test_guild, test_user)

    async def test_missing_message_id_raises(self):
        """egg with no message_id stored - should raise before attempting fetch"""
        egg = _make_egg(hatches_at=100.0, result='🐣', message_id=None)  # pyright: ignore[reportArgumentType]
        self.egg_repo.get_oldest_ready.return_value = egg

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        self.mock_bot.get_channel.return_value = MagicMock()

        with pytest.raises(RuntimeError, match='no message_id'):
            await hatch_egg(test_guild, test_user)


# ============================================================
# egg commands (commands.py)
# ============================================================


class TestEggCommands:
    @pytest.fixture(autouse=True)
    def setup(self, make_guild, mock_ctx_factory):
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.guild_id = test_guild
        self.ctx = ctx

    async def test_egg_command_success(self):
        with patch('attubot.eggs.commands.hatching.collect_egg', new=AsyncMock(return_value='https://discord.com/channels/1/2/3')):
            from attubot.eggs.commands import egg_command

            await egg_command(self.ctx)

        assert 'discord.com' in self.ctx._responses[0]['args'][0]

    async def test_egg_command_cooldown(self):
        with patch('attubot.eggs.commands.hatching.collect_egg', new=AsyncMock(side_effect=ValueError('try again in 5m 0s'))):
            from attubot.eggs.commands import egg_command

            await egg_command(self.ctx)

        assert self.ctx._responses[0]['kwargs'].get('ephemeral') is True
        assert 'try again' in self.ctx._responses[0]['args'][0]

    async def test_egg_command_unauthorized(self, mock_ctx_factory):
        ctx = mock_ctx_factory()
        ctx.guild_id = 9999999999  # not in authorized_guilds
        from attubot.eggs.commands import egg_command

        await egg_command(ctx)
        assert ctx._responses[0]['args'][0] == 'not available here'

    async def test_eggs_hatch_no_eggs(self):
        with patch('attubot.eggs.commands.hatching.hatch_egg', new=AsyncMock(return_value=('no_eggs', None))):
            from attubot.eggs.commands import eggs_hatch

            await eggs_hatch(self.ctx)
        assert self.ctx._responses[0]['args'][0] == 'you have no eggs'

    async def test_eggs_hatch_not_ready(self):
        with patch('attubot.eggs.commands.hatching.hatch_egg', new=AsyncMock(return_value=('', 9999.0))):
            from attubot.eggs.commands import eggs_hatch

            await eggs_hatch(self.ctx)
        assert '<t:9999:R>' in self.ctx._responses[0]['args'][0]

    async def test_eggs_hatch_ready(self):
        with patch('attubot.eggs.commands.hatching.hatch_egg', new=AsyncMock(return_value=('https://discord.com/channels/1/2/3', None))):
            from attubot.eggs.commands import eggs_hatch

            await eggs_hatch(self.ctx)
        assert 'hatching' in self.ctx._responses[0]['args'][0]

    async def test_eggs_view_no_thread(self):
        with patch.object(hatching_mod, '_egg_user_repo') as mock_repo:
            mock_repo.get = AsyncMock(return_value=None)
            from attubot.eggs.commands import eggs_view

            await eggs_view(self.ctx)
        assert "haven't collected" in self.ctx._responses[0]['args'][0]

    async def test_eggs_view_has_thread(self):
        user_doc = _make_user_doc(thread_id=test_thread)
        with patch.object(hatching_mod, '_egg_user_repo') as mock_repo:
            mock_repo.get = AsyncMock(return_value=user_doc)
            from attubot.eggs.commands import eggs_view

            await eggs_view(self.ctx)
        assert str(test_thread) in self.ctx._responses[0]['args'][0]


# ============================================================
# emojis.py
# ============================================================


class TestEmojis:
    async def test_render_egg_swaps_class(self):
        """render_egg replaces 'common' class with the given rarity in the svg"""
        fake_png = b'fakepng'
        with patch('attubot.eggs.emojis.svg_to_png', new=AsyncMock(return_value=fake_png)) as mock_svg:
            from attubot.eggs.emojis import render_egg

            result = await render_egg('rare')

        assert result == fake_png
        svg_text = mock_svg.call_args.args[0]
        assert 'class="rare"' in svg_text
        assert 'class="common"' not in svg_text

    async def test_ensure_egg_emojis_creates_missing(self):
        """emojis not on guild should be uploaded via create_custom_emoji"""
        mock_emoji = MagicMock()
        mock_guild = MagicMock()
        mock_guild.emojis = []
        mock_guild.create_custom_emoji = AsyncMock(return_value=mock_emoji)

        with patch('attubot.eggs.emojis.render_egg', new=AsyncMock(return_value=b'png')):
            from attubot.eggs.emojis import ensure_egg_emojis

            result = await ensure_egg_emojis(mock_guild)

        assert len(result) == 5  # one per rarity
        assert mock_guild.create_custom_emoji.call_count == 5

    async def test_ensure_egg_emojis_reuses_existing(self):
        """emojis already on guild should not trigger create_custom_emoji"""
        from attubot.eggs.data import rarities

        existing = []
        for r in rarities:
            e = MagicMock()
            e.name = f'{r}_egg'
            existing.append(e)

        mock_guild = MagicMock()
        mock_guild.emojis = existing
        mock_guild.create_custom_emoji = AsyncMock()

        from attubot.eggs.emojis import ensure_egg_emojis

        result = await ensure_egg_emojis(mock_guild)

        assert len(result) == 5
        mock_guild.create_custom_emoji.assert_not_called()
