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

import doom_bot.eggs.hatching as hatching_mod
from doom_bot.database.models import EggDocument, EggUserDocument
from doom_bot.eggs.hatching import (
    _egg_emoji_str,
    collect_egg,
    ensure_eggs_ready,
    hatch_date,
    hatch_egg,
    run_hatch_animation,
)
from doom_bot.tasks.egg_cleanup import egg_cleanup_task
from doom_bot.tasks.scheduler import scheduler as real_scheduler


# ---- constants ----

test_guild = 1234567890
test_user = 9876543210
test_user2 = 1111111111
test_thread = 5555555555
test_message = 222222222222


# ---- helpers ----


def _make_egg(*, hatched=False, hatches_at=0, message_id=test_message, rarity='common', result='🐣'):
    return EggDocument(
        egg_id='test-egg-id',
        guild_id=test_guild,
        user_id=test_user,
        rarity=rarity,
        collected_at=1000,
        hatches_at=hatches_at,
        hatched=hatched,
        result=result,
        message_id=message_id,
    )


def _make_user_doc(*, thread_id=test_thread, last_collected_at=0):
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
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
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

        with patch('doom_bot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg
            mock_config.hatch.tuning.collect_cooldown_seconds = 600
            mock_config.hatch.rarities = ['common']
            mock_config.hatch.drop_weights = [1]
            mock_config.hatch.pools = {'common': ['🐣']}
            mock_config.hatch.hatch_durations = {'common': 1800}

            result, remaining = await collect_egg(test_guild, test_user, 'testuser')

        assert isinstance(result, str)
        assert 'discord.com' in result
        assert remaining is None
        self.egg_repo.insert.assert_called_once()
        # upsert called twice for new user: once in get_or_create_user_thread, once to update cooldown
        assert self.egg_user_repo.upsert.call_count == 2

    async def test_cooldown_active_raises(self):
        """user collected 60s ago - still within 600s cooldown"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=int(time.time()) - 60)

        with patch('doom_bot.eggs.hatching.config') as mock_config:
            mock_config.hatch.tuning.collect_cooldown_seconds = 600
            result, remaining = await collect_egg(test_guild, test_user, 'testuser')

        assert result == 'cooldown'
        assert remaining is not None
        assert remaining > time.time()  # ready_at is a future unix timestamp

    async def test_cooldown_expired_succeeds(self):
        """user collected 1000s ago - cooldown has elapsed"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=int(time.time()) - 1000)
        self.egg_user_repo.upsert.return_value = None
        self.egg_repo.insert.return_value = None

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = test_thread

        with patch('doom_bot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg
            mock_config.hatch.tuning.collect_cooldown_seconds = 600
            mock_config.hatch.rarities = ['common']
            mock_config.hatch.drop_weights = [1]
            mock_config.hatch.pools = {'common': ['🐣']}
            mock_config.hatch.hatch_durations = {'common': 1800}

            result, remaining = await collect_egg(test_guild, test_user, 'testuser')

        assert isinstance(result, str)
        assert remaining is None
        self.egg_repo.insert.assert_called_once()


# ============================================================
# hatch_egg()
# ============================================================


class TestHatchEgg:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()
        hatching_mod._hatch_last_used.clear()

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
            patch.object(real_scheduler, 'add_job') as mock_add_job,
        ):
            mock_config.hatch.tuning.hatch_cooldown_seconds = 5
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_config = mock_config
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
        next_egg = _make_egg(hatches_at=9999)
        self.egg_repo.get_next_unhatched.return_value = next_egg

        result, ts = await hatch_egg(test_guild, test_user)

        assert result == ''
        assert ts == 9999

    async def test_egg_ready(self):
        egg = _make_egg(hatches_at=100, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        self.egg_repo.mark_hatched.return_value = None

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_msg = AsyncMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.get_partial_message = MagicMock(return_value=mock_msg)
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

        with (
            patch('doom_bot.eggs.hatching.asyncio') as mock_asyncio,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            mock_asyncio.sleep = AsyncMock(side_effect=fake_sleep)
            mock_config.hatch.tuning.animation_wait_min = 10
            mock_config.hatch.tuning.animation_wait_max = 15

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
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
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
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
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
        with patch('doom_bot.eggs.hatching.config') as mock_config:
            mock_config.theme.egg_emojis.get.return_value = 123456789
            result = _egg_emoji_str('common')
        assert result == '<:common_egg:123456789>'

    def test_without_emoji_id_returns_fallback(self):
        with patch('doom_bot.eggs.hatching.config') as mock_config:
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
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_config = mock_config
            yield

    async def test_thread_cache_miss_fetches_from_api(self):
        """thread in user_doc but not in bot cache - fetches via guild api"""
        from doom_bot.eggs.hatching import get_or_create_user_thread

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
        from doom_bot.eggs.hatching import get_or_create_user_thread

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
        hatching_mod._hatch_last_used.clear()

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
            patch.object(real_scheduler, 'add_job') as mock_add_job,
        ):
            mock_config.hatch.tuning.hatch_cooldown_seconds = 5
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_add_job = mock_add_job
            yield

    async def test_thread_cache_miss_fetches_from_guild(self):
        """thread not in bot cache - should fetch via guild api"""
        egg = _make_egg(hatches_at=100, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        self.egg_repo.mark_hatched.return_value = None

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_msg = AsyncMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.get_partial_message = MagicMock(return_value=mock_msg)

        mock_guild = MagicMock()
        mock_guild.fetch_channel = AsyncMock(return_value=mock_thread)

        self.mock_bot.get_channel.return_value = None
        self.mock_bot.get_guild.return_value = mock_guild

        result, _ = await hatch_egg(test_guild, test_user)

        assert 'discord.com' in result
        mock_guild.fetch_channel.assert_called_once_with(test_thread)

    async def test_guild_cache_miss_raises(self):
        """both thread and guild not in cache - should raise"""
        egg = _make_egg(hatches_at=100, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        self.mock_bot.get_channel.return_value = None
        self.mock_bot.get_guild.return_value = None

        with pytest.raises(RuntimeError, match='not in cache'):
            await hatch_egg(test_guild, test_user)

    async def test_missing_message_id_raises(self):
        """egg with no message_id stored - should raise before attempting fetch"""
        egg = _make_egg(hatches_at=100, result='🐣', message_id=None)  # pyright: ignore[reportArgumentType]
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
        with patch('doom_bot.commands.eggs.hatching.collect_egg', new=AsyncMock(return_value=('https://discord.com/channels/1/2/3', None))):
            from doom_bot.commands.eggs import egg_command

            await egg_command(self.ctx)

        assert 'discord.com' in self.ctx._responses[0]['args'][0]

    async def test_egg_command_cooldown(self):
        ready_at = time.time() + 300
        with patch('doom_bot.commands.eggs.hatching.collect_egg', new=AsyncMock(return_value=('cooldown', ready_at))):
            from doom_bot.commands.eggs import egg_command

            await egg_command(self.ctx)

        assert self.ctx._responses[0]['kwargs'].get('ephemeral') is True
        assert 'try again' in self.ctx._responses[0]['args'][0]
        assert f'<t:{int(ready_at)}:R>' in self.ctx._responses[0]['args'][0]

    async def test_egg_command_unauthorized(self, mock_ctx_factory):
        ctx = mock_ctx_factory()
        ctx.guild_id = 9999999999  # not in authorized_guilds
        from doom_bot.commands.eggs import egg_command

        await egg_command(ctx)
        assert ctx._responses[0]['args'][0] == 'not available here'

    async def test_eggs_hatch_no_eggs(self):
        with patch('doom_bot.commands.eggs.hatching.hatch_egg', new=AsyncMock(return_value=('no_eggs', None))):
            from doom_bot.commands.eggs import eggs_hatch

            await eggs_hatch(self.ctx)
        assert self.ctx._responses[0]['args'][0] == 'you have no eggs'

    async def test_eggs_hatch_not_ready(self):
        with patch('doom_bot.commands.eggs.hatching.hatch_egg', new=AsyncMock(return_value=('', 9999.0))):
            from doom_bot.commands.eggs import eggs_hatch

            await eggs_hatch(self.ctx)
        assert '<t:9999:R>' in self.ctx._responses[0]['args'][0]

    async def test_eggs_hatch_ready(self):
        with patch('doom_bot.commands.eggs.hatching.hatch_egg', new=AsyncMock(return_value=('https://discord.com/channels/1/2/3', None))):
            from doom_bot.commands.eggs import eggs_hatch

            await eggs_hatch(self.ctx)
        assert 'hatching' in self.ctx._responses[0]['args'][0]

    async def test_eggs_view_no_thread(self):
        with patch.object(hatching_mod, '_egg_user_repo') as mock_repo:
            mock_repo.get = AsyncMock(return_value=None)
            from doom_bot.commands.eggs import eggs_view

            await eggs_view(self.ctx)
        assert "haven't collected" in self.ctx._responses[0]['args'][0]

    async def test_eggs_view_has_thread(self):
        user_doc = _make_user_doc(thread_id=test_thread)
        with patch.object(hatching_mod, '_egg_user_repo') as mock_repo:
            mock_repo.get = AsyncMock(return_value=user_doc)
            from doom_bot.commands.eggs import eggs_view

            await eggs_view(self.ctx)
        assert str(test_thread) in self.ctx._responses[0]['args'][0]


# ============================================================
# /eggs progress command
# ============================================================


class TestEggsProgress:
    @pytest.fixture(autouse=True)
    def setup(self, make_guild, mock_ctx_factory):
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.guild_id = test_guild
        ctx.author.display_name = 'TestPlayer'
        self.ctx = ctx

    async def test_embed_title_includes_display_name(self):
        """embed title is "{display_name}'s egg collection" """
        with (
            patch.object(hatching_mod, '_egg_repo') as mock_repo,
            patch('doom_bot.eggs.emojis.render_progress_bar', return_value='▓▓▓░░░░░░░'),
            patch('doom_bot.commands.eggs.config') as mock_config,
        ):
            mock_config.authorized_guilds = {test_guild}
            mock_config.hatch.rarities = ['common']
            mock_config.hatch.pools = {'common': ['🐣']}
            mock_repo.get_user_egg_stats = AsyncMock(return_value=(10, 5, {'common': 1}))
            from doom_bot.commands.eggs import eggs_progress

            await eggs_progress(self.ctx)

        embed = self.ctx._responses[0]['kwargs']['embed']
        assert embed.title == "TestPlayer's egg collection"


# ============================================================
# /eggs leaderboard hatched command
# ============================================================


class TestEggsLeaderboardHatched:
    @pytest.fixture(autouse=True)
    def setup(self, make_guild, mock_ctx_factory):
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.guild_id = test_guild
        self.ctx = ctx

    async def test_unauthorized_guild(self, mock_ctx_factory):
        ctx = mock_ctx_factory()
        ctx.guild_id = 9999999999
        from doom_bot.commands.eggs import eggs_leaderboard_hatched

        await eggs_leaderboard_hatched(ctx)
        assert ctx._responses[0]['args'][0] == 'not available here'
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_with_data(self):
        """leaderboard has data - embed description shows user mention and count"""
        rows = [{'_id': test_user, 'total': 7}]
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.leaderboard_most_hatched = AsyncMock(return_value=rows)
            from doom_bot.commands.eggs import eggs_leaderboard_hatched

            await eggs_leaderboard_hatched(self.ctx)
        embed = self.ctx._responses[0]['kwargs']['embed']
        assert f'<@{test_user}>' in embed.description
        assert '**7**' in embed.description

    async def test_empty(self):
        """repo returns no data - embed description shows 'no data yet'"""
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.leaderboard_most_hatched = AsyncMock(return_value=[])
            from doom_bot.commands.eggs import eggs_leaderboard_hatched

            await eggs_leaderboard_hatched(self.ctx)
        embed = self.ctx._responses[0]['kwargs']['embed']
        assert embed.description == 'no data yet'


# ============================================================
# /eggs leaderboard collected command
# ============================================================


class TestEggsLeaderboardCollected:
    @pytest.fixture(autouse=True)
    def setup(self, make_guild, mock_ctx_factory):
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.guild_id = test_guild
        self.ctx = ctx

    async def test_unauthorized_guild(self, mock_ctx_factory):
        ctx = mock_ctx_factory()
        ctx.guild_id = 9999999999
        from doom_bot.commands.eggs import eggs_leaderboard_collected

        await eggs_leaderboard_collected(ctx)
        assert ctx._responses[0]['args'][0] == 'not available here'
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_with_data(self):
        """leaderboard has data - embed description shows user mention and unique count"""
        rows = [{'_id': test_user2, 'unique': 3}]
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.leaderboard_most_unique = AsyncMock(return_value=rows)
            from doom_bot.commands.eggs import eggs_leaderboard_collected

            await eggs_leaderboard_collected(self.ctx)
        embed = self.ctx._responses[0]['kwargs']['embed']
        assert f'<@{test_user2}>' in embed.description
        assert '**3**' in embed.description

    async def test_empty(self):
        """repo returns no data - embed description shows 'no data yet'"""
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.leaderboard_most_unique = AsyncMock(return_value=[])
            from doom_bot.commands.eggs import eggs_leaderboard_collected

            await eggs_leaderboard_collected(self.ctx)
        embed = self.ctx._responses[0]['kwargs']['embed']
        assert embed.description == 'no data yet'


# ============================================================
# emojis.py
# ============================================================


class TestEmojis:
    async def test_render_egg_swaps_class(self):
        """render_egg replaces 'common' class with the given rarity in the svg"""
        fake_png = b'fakepng'
        with patch('doom_bot.eggs.emojis.svg_to_png', new=AsyncMock(return_value=fake_png)) as mock_svg:
            from doom_bot.eggs.emojis import render_egg

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

        with (
            patch('doom_bot.eggs.emojis.render_egg', new=AsyncMock(return_value=b'png')),
            patch('doom_bot.client.core.config') as mock_config,
        ):
            mock_config.hatch.rarities = ['common', 'uncommon', 'rare', 'legendary', 'mythical']
            from doom_bot.eggs.emojis import ensure_egg_emojis

            result = await ensure_egg_emojis(mock_guild)

        assert len(result) == 5  # one per rarity
        assert mock_guild.create_custom_emoji.call_count == 5

    async def test_ensure_egg_emojis_reuses_existing(self):
        """emojis already on guild should not trigger create_custom_emoji"""
        rarities = ['common', 'uncommon', 'rare', 'legendary', 'mythical']

        existing = []
        for r in rarities:
            e = MagicMock()
            e.name = f'{r}_egg'
            existing.append(e)

        mock_guild = MagicMock()
        mock_guild.emojis = existing
        mock_guild.create_custom_emoji = AsyncMock()

        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.hatch.rarities = rarities
            from doom_bot.eggs.emojis import ensure_egg_emojis

            result = await ensure_egg_emojis(mock_guild)

        assert len(result) == 5
        mock_guild.create_custom_emoji.assert_not_called()


# ============================================================
# transfer_egg()
# ============================================================


class TestTransferEgg:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()

        mock_old_msg = AsyncMock()
        mock_new_msg = MagicMock()
        mock_new_msg.id = 333333333333
        mock_new_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/333333333333'

        mock_thread = MagicMock()
        mock_thread.get_partial_message = MagicMock(return_value=mock_old_msg)
        mock_thread.send = AsyncMock(return_value=mock_new_msg)

        # both from-user and to-user get a doc with the same test_thread (simpler mocking)
        async def mock_user_get(guild_id, user_id):
            return EggUserDocument(guild_id=guild_id, user_id=user_id, thread_id=test_thread)

        mock_egg_user_repo.get = AsyncMock(side_effect=mock_user_get)

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            mock_bot.get_channel.return_value = mock_thread
            mock_guild_cfg = MagicMock()
            mock_guild_cfg.channels.eggs = test_thread
            mock_config.guild.return_value = mock_guild_cfg

            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.old_msg = mock_old_msg
            self.new_msg = mock_new_msg
            self.thread = mock_thread
            yield

    async def test_transfer_succeeds(self):
        """happy path: deletes old message, reposts in recipient thread, updates db"""
        from doom_bot.eggs.hatching import transfer_egg

        egg = _make_egg(result='🐣', hatched=False)
        self.egg_repo.get.return_value = egg

        result = await transfer_egg(test_guild, egg.egg_id, test_user, test_user2, 'user2')

        assert 'discord.com' in result
        self.old_msg.delete.assert_called_once()
        self.egg_repo.transfer.assert_called_once_with(egg.egg_id, test_user2, self.new_msg.id)

    async def test_transfer_hatched_uses_result_emoji(self):
        """hatched egg reposts the creature emoji, not the egg emoji"""
        from doom_bot.eggs.hatching import transfer_egg

        egg = _make_egg(hatched=True, result='🦄')
        self.egg_repo.get.return_value = egg

        await transfer_egg(test_guild, egg.egg_id, test_user, test_user2, 'user2')

        send_call_content = self.thread.send.call_args.args[0]
        assert send_call_content == '🦄'

    async def test_transfer_wrong_owner_raises(self):
        """egg belongs to a different user - should raise ValueError"""
        from doom_bot.eggs.hatching import transfer_egg

        egg = _make_egg()  # user_id=test_user
        self.egg_repo.get.return_value = egg

        with pytest.raises(ValueError, match='egg not found'):
            await transfer_egg(test_guild, egg.egg_id, test_user2, test_user, 'user1')  # from_user is test_user2, not owner

    async def test_transfer_egg_not_in_db_raises(self):
        """egg not found in db - should raise ValueError"""
        from doom_bot.eggs.hatching import transfer_egg

        self.egg_repo.get.return_value = None

        with pytest.raises(ValueError, match='egg not found'):
            await transfer_egg(test_guild, 'missing-egg-id', test_user, test_user2, 'user2')

    async def test_transfer_old_message_missing_proceeds(self):
        """original thread message already deleted - should proceed without error"""
        from doom_bot.eggs.hatching import transfer_egg

        egg = _make_egg()
        self.egg_repo.get.return_value = egg
        self.old_msg.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))

        result = await transfer_egg(test_guild, egg.egg_id, test_user, test_user2, 'user2')

        assert 'discord.com' in result
        self.egg_repo.transfer.assert_called_once()


# ============================================================
# _offer_text() helper
# ============================================================


class TestOfferText:
    def test_unhatched_egg_shows_rarity(self):
        """unhatched egg - shows rarity emoji and rarity name"""
        from doom_bot.commands.eggs import _offer_text

        egg = _make_egg(hatched=False, rarity='rare')

        with patch('doom_bot.eggs.hatching._egg_emoji_str', return_value='<:rare_egg:999>'):
            result = _offer_text('<@1>', '<@2>', egg, '')

        assert '<:rare_egg:999>' in result
        assert 'rare egg' in result
        assert '<@1>' in result
        assert '<@2>' in result

    def test_hatched_egg_shows_creature(self):
        """hatched egg - shows creature emoji directly"""
        from doom_bot.commands.eggs import _offer_text

        egg = _make_egg(hatched=True, result='🦄')

        result = _offer_text('<@1>', '<@2>', egg, '')

        assert '🦄' in result
        assert 'egg' not in result

    def test_includes_jump_url_when_provided(self):
        """jump url is appended when non-empty"""
        from doom_bot.commands.eggs import _offer_text

        egg = _make_egg(hatched=True, result='🐉')
        url = 'https://discord.com/channels/1/2/3'

        result = _offer_text('<@1>', '<@2>', egg, url)

        assert url in result

    def test_no_jump_url_no_suffix(self):
        """empty jump url - no extra newline or text appended"""
        from doom_bot.commands.eggs import _offer_text

        egg = _make_egg(hatched=True, result='🐉')

        result = _offer_text('<@1>', '<@2>', egg, '')

        assert '\n' not in result


# ============================================================
# EggGiftOfferView - button callbacks
# ============================================================


def _make_interaction(user_id: int) -> MagicMock:
    """Create a minimal mock discord.Interaction for view callback testing."""
    interaction = MagicMock()
    interaction.user = MagicMock()
    interaction.user.id = user_id
    interaction.response = AsyncMock()
    interaction.response.edit_message = AsyncMock()
    interaction.response.send_message = AsyncMock()
    return interaction


def _make_offer_view(egg: EggDocument | None = None):
    from doom_bot.commands.eggs import EggGiftOfferView

    if egg is None:
        egg = _make_egg()
    return EggGiftOfferView(egg, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)


class TestEggGiftOfferView:
    async def test_accept_transfers_egg_and_edits_sent(self):
        """recipient accepts - transfer_egg called, message edited to 'sent!'"""
        from doom_bot.commands.eggs import EggGiftOfferView

        view = _make_offer_view()
        interaction = _make_interaction(test_user2)

        with patch('doom_bot.commands.eggs.hatching.transfer_egg', new=AsyncMock(return_value='https://discord.com/1/2/3')):
            await EggGiftOfferView.accept(view, MagicMock(), interaction)  # pyright: ignore[reportCallIssue]

        interaction.response.edit_message.assert_called_once()
        content = interaction.response.edit_message.call_args.kwargs['content']
        assert content.startswith('sent!')
        assert 'https://discord.com/1/2/3' in content

    async def test_accept_wrong_user_gets_ephemeral_error(self):
        """non-recipient clicking Accept gets ephemeral rejection"""
        from doom_bot.commands.eggs import EggGiftOfferView

        view = _make_offer_view()
        interaction = _make_interaction(test_user)  # giver, not recipient

        await EggGiftOfferView.accept(view, MagicMock(), interaction)  # pyright: ignore[reportCallIssue]

        interaction.response.send_message.assert_called_once()
        assert interaction.response.send_message.call_args.kwargs.get('ephemeral') is True
        interaction.response.edit_message.assert_not_called()

    async def test_accept_egg_gone_edits_no_longer_available(self):
        """transfer_egg raises ValueError - message edited to 'no longer available'"""
        from doom_bot.commands.eggs import EggGiftOfferView

        view = _make_offer_view()
        interaction = _make_interaction(test_user2)

        with patch('doom_bot.commands.eggs.hatching.transfer_egg', new=AsyncMock(side_effect=ValueError('egg not found'))):
            await EggGiftOfferView.accept(view, MagicMock(), interaction)  # pyright: ignore[reportCallIssue]

        content = interaction.response.edit_message.call_args.kwargs['content']
        assert 'no longer available' in content

    async def test_decline_edits_offer_declined(self):
        """recipient declines - message edited with their mention"""
        from doom_bot.commands.eggs import EggGiftOfferView

        view = _make_offer_view()
        interaction = _make_interaction(test_user2)

        await EggGiftOfferView.decline(view, MagicMock(), interaction)  # pyright: ignore[reportCallIssue]

        content = interaction.response.edit_message.call_args.kwargs['content']
        assert content == f'<@{test_user2}> said no'

    async def test_decline_wrong_user_gets_ephemeral_error(self):
        """non-recipient clicking Decline gets ephemeral rejection"""
        from doom_bot.commands.eggs import EggGiftOfferView

        view = _make_offer_view()
        interaction = _make_interaction(test_user)  # giver, not recipient

        await EggGiftOfferView.decline(view, MagicMock(), interaction)  # pyright: ignore[reportCallIssue]

        interaction.response.send_message.assert_called_once()
        assert interaction.response.send_message.call_args.kwargs.get('ephemeral') is True
        interaction.response.edit_message.assert_not_called()

    async def test_timeout_edits_offer_expired(self):
        """view timeout - message edited with recipient mention"""
        view = _make_offer_view()
        mock_message = AsyncMock()
        view.message = mock_message

        await view.on_timeout()

        mock_message.edit.assert_called_once_with(content=f'<@{test_user2}> took too long', view=None)

    async def test_timeout_no_message_is_noop(self):
        """timeout with no message stored - should not raise"""
        view = _make_offer_view()
        view.message = None

        await view.on_timeout()  # no error


# ============================================================
# _EggSelectMenu - callback
# ============================================================


def _make_select_menu(options: list | None = None):
    from doom_bot.commands.eggs import _EggSelectMenu

    if options is None:
        options = [discord.SelectOption(label='common egg', value='unhatched:common')]
    return _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)


class TestEggSelectMenu:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()
        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
        ):
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            yield

    async def test_select_unhatched_posts_offer(self):
        """selecting an unhatched rarity queries by rarity and posts offer"""
        select = _make_select_menu()
        select._interaction = MagicMock()
        select._selected_values = ['unhatched:common']

        egg = _make_egg(rarity='common', hatched=False)
        self.egg_repo.get_oldest_unhatched_by_rarity = AsyncMock(return_value=egg)
        self.egg_user_repo.get = AsyncMock(return_value=_make_user_doc())

        interaction = _make_interaction(test_user)
        interaction.channel = AsyncMock()
        interaction.channel.send = AsyncMock(return_value=MagicMock())

        with patch('doom_bot.eggs.hatching._egg_emoji_str', return_value='<:common_egg:1>'):
            await select.callback(interaction)

        self.egg_repo.get_oldest_unhatched_by_rarity.assert_called_once_with(test_guild, test_user, 'common')
        interaction.channel.send.assert_called_once()
        interaction.response.edit_message.assert_called_once_with(content='offer sent!', view=None)

    async def test_select_hatched_posts_offer(self):
        """selecting a hatched creature queries by result emoji and posts offer"""
        select = _make_select_menu(options=[discord.SelectOption(label='🦄', value='hatched:🦄')])
        select._interaction = MagicMock()
        select._selected_values = ['hatched:🦄']

        egg = _make_egg(hatched=True, result='🦄')
        self.egg_repo.get_oldest_hatched_by_result = AsyncMock(return_value=egg)
        self.egg_user_repo.get = AsyncMock(return_value=_make_user_doc())

        interaction = _make_interaction(test_user)
        interaction.channel = AsyncMock()
        interaction.channel.send = AsyncMock(return_value=MagicMock())

        await select.callback(interaction)

        self.egg_repo.get_oldest_hatched_by_result.assert_called_once_with(test_guild, test_user, '🦄')
        interaction.channel.send.assert_called_once()

    async def test_select_wrong_user_gets_ephemeral_error(self):
        """non-giver interacting with select gets ephemeral rejection"""
        select = _make_select_menu()

        interaction = _make_interaction(test_user2)  # recipient, not giver

        await select.callback(interaction)

        interaction.response.send_message.assert_called_once()
        assert interaction.response.send_message.call_args.kwargs.get('ephemeral') is True

    async def test_select_egg_gone_edits_message(self):
        """egg no longer exists when selected - message edited to 'no longer available'"""
        select = _make_select_menu()
        select._interaction = MagicMock()
        select._selected_values = ['unhatched:common']

        self.egg_repo.get_oldest_unhatched_by_rarity = AsyncMock(return_value=None)

        interaction = _make_interaction(test_user)

        await select.callback(interaction)

        content = interaction.response.edit_message.call_args.kwargs['content']
        assert 'no longer available' in content


# ============================================================
# _EggSelectMenu - pagination
# ============================================================


def _make_options(count: int) -> list[discord.SelectOption]:
    """build a list of n unique select options for pagination tests."""
    return [discord.SelectOption(label=f'creature {i}', value=f'hatched:creature_{i}') for i in range(count)]


class TestEggSelectMenuPagination:
    def test_under_page_size_no_more_option(self):
        """fewer than 24 items - no 'more' option appended"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(10)
        menu = _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(menu.options) == 10
        assert all(not o.value.startswith('more:') for o in menu.options)

    def test_exactly_page_size_no_more_option(self):
        """exactly 24 items - no 'more' option needed"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(24)
        menu = _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(menu.options) == 24
        assert all(not o.value.startswith('more:') for o in menu.options)

    def test_over_page_size_adds_more_option(self):
        """25+ items - first page has 24 items + 1 'more' option = 25 total"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(30)
        menu = _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(menu.options) == 25
        assert menu.options[-1].value == 'more:24'
        assert menu.options[-1].label == 'more...'

    def test_second_page_remainder(self):
        """30 items starting at offset 24 - second page has 6 items, no 'more'"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(30)
        menu = _EggSelectMenu(options, 24, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(menu.options) == 6
        assert all(not o.value.startswith('more:') for o in menu.options)

    def test_multi_page_chain(self):
        """49 items - page 1 has 'more:24', page 2 has 'more:48', page 3 has 1 item"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(49)

        # page 1
        p1 = _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(p1.options) == 25
        assert p1.options[-1].value == 'more:24'

        # page 2
        p2 = _EggSelectMenu(options, 24, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(p2.options) == 25
        assert p2.options[-1].value == 'more:48'

        # page 3
        p3 = _EggSelectMenu(options, 48, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
        assert len(p3.options) == 1
        assert not p3.options[0].value.startswith('more:')

    def test_no_page_exceeds_25_options(self):
        """exhaustive check: for a large list, every page has at most 25 options"""
        from doom_bot.commands.eggs import _EggSelectMenu

        options = _make_options(100)
        offset = 0
        pages_seen = 0
        while offset < len(options):
            menu = _EggSelectMenu(options, offset, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)
            assert len(menu.options) <= 25
            pages_seen += 1
            # check if last option is a 'more' link
            if menu.options[-1].value.startswith('more:'):
                offset = int(menu.options[-1].value[5:])
            else:
                break
        # should have visited all items across all pages
        assert pages_seen == 5  # ceil(100 / 24) = 5 pages

    async def test_more_callback_advances_page(self):
        """selecting 'more:24' edits the message with a new view at offset 24"""
        from doom_bot.commands.eggs import EggSelectView, _EggSelectMenu

        options = _make_options(30)
        menu = _EggSelectMenu(options, 0, test_user, f'<@{test_user}>', test_user2, f'<@{test_user2}>', 'user2', test_guild)

        # simulate user selecting the 'more' option
        menu._selected_values = ['more:24']
        menu._interaction = MagicMock()  # pycord requires _interaction for values property

        interaction = _make_interaction(test_user)
        await menu.callback(interaction)

        interaction.response.edit_message.assert_called_once()
        call_kwargs = interaction.response.edit_message.call_args.kwargs
        assert call_kwargs['content'] == 'pick an egg to give:'
        new_view = call_kwargs['view']
        assert isinstance(new_view, EggSelectView)
        # the new view's select menu should have 6 items (30 - 24)
        new_select = new_view.children[0]
        assert len(new_select.options) == 6


# ============================================================
# /eggs give command
# ============================================================


class TestEggsGiveCommand:
    @pytest.fixture(autouse=True)
    def setup(self, make_guild, mock_ctx_factory):
        make_guild(guild_id=test_guild)
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.guild_id = test_guild
        ctx.channel.send = AsyncMock(return_value=MagicMock())
        self.ctx = ctx

        self.mock_user = MagicMock()
        self.mock_user.id = test_user2
        self.mock_user.mention = f'<@{test_user2}>'
        self.mock_user.display_name = 'user2'

    async def test_unauthorized_guild(self, mock_ctx_factory):
        ctx = mock_ctx_factory()
        ctx.guild_id = 9999999999
        ctx.channel.send = AsyncMock()

        from doom_bot.commands.eggs import eggs_give

        await eggs_give(ctx, self.mock_user, None)
        assert ctx._responses[0]['args'][0] == 'not available here'

    async def test_give_to_self(self):
        """giving an egg to yourself is rejected"""
        self.ctx.author.id = test_user2  # same as mock_user.id
        from doom_bot.commands.eggs import eggs_give

        await eggs_give(self.ctx, self.mock_user, None)
        assert 'yourself' in self.ctx._responses[0]['args'][0]

    async def test_unhatched_filter_shows_unhatched_select_menu(self):
        """filter='unhatched' - shows select menu of unique unhatched rarities only"""
        unhatched = [_make_egg(rarity='rare'), _make_egg(rarity='common')]

        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.list_unhatched = AsyncMock(return_value=unhatched)

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, 'unhatched')

        response = self.ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        select = response['kwargs']['view'].children[0]
        assert len(select.options) == 2  # rare, common

    async def test_unhatched_filter_no_eggs(self):
        """filter='unhatched' but user has no unhatched eggs"""
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.list_unhatched = AsyncMock(return_value=[])

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, 'unhatched')

        response = self.ctx._responses[0]
        assert 'unhatched eggs' in response['args'][0]
        assert response['kwargs'].get('ephemeral') is True

    async def test_no_rarity_shows_select_menu(self):
        """no rarity arg - ephemeral select menu shown with deduped options"""
        unhatched = [
            _make_egg(rarity='common'),
            _make_egg(rarity='common'),  # duplicate - should be deduped
            _make_egg(rarity='rare'),
        ]
        hatched_eggs = [_make_egg(hatched=True, result='🦄')]

        with (
            patch.object(hatching_mod, '_egg_repo') as mock_repo,
        ):
            mock_repo.list_unhatched = AsyncMock(return_value=unhatched)
            mock_repo.list_hatched = AsyncMock(return_value=hatched_eggs)

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, None)

        response = self.ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        # view should have been passed; check the select options count (2 unique rarities + 1 hatched)
        view = response['kwargs']['view']
        select = view.children[0]
        assert len(select.options) == 3  # common, rare, 🦄

    async def test_no_rarity_no_eggs_at_all(self):
        """no rarity arg, user has no eggs - ephemeral error"""
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.list_unhatched = AsyncMock(return_value=[])
            mock_repo.list_hatched = AsyncMock(return_value=[])

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, None)

        response = self.ctx._responses[0]
        assert 'no eggs' in response['args'][0]
        assert response['kwargs'].get('ephemeral') is True

    async def test_hatched_arg_shows_creature_select_menu(self):
        """rarity='hatched' - shows select menu of unique hatched creatures"""
        hatched_eggs = [
            _make_egg(hatched=True, result='🦄'),
            _make_egg(hatched=True, result='🦄'),  # duplicate
            _make_egg(hatched=True, result='🐉'),
        ]

        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.list_hatched = AsyncMock(return_value=hatched_eggs)

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, 'hatched')

        response = self.ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        select = response['kwargs']['view'].children[0]
        assert len(select.options) == 2  # 🦄 and 🐉 (deduped)

    async def test_hatched_arg_no_hatched_eggs(self):
        """rarity='hatched' but user has no hatched eggs"""
        with patch.object(hatching_mod, '_egg_repo') as mock_repo:
            mock_repo.list_hatched = AsyncMock(return_value=[])

            from doom_bot.commands.eggs import eggs_give

            await eggs_give(self.ctx, self.mock_user, 'hatched')

        response = self.ctx._responses[0]
        assert 'hatched eggs' in response['args'][0]
        assert response['kwargs'].get('ephemeral') is True


# ============================================================
# ensure_eggs_ready() coverage
# ============================================================


class TestEnsureEggsReadyExtra:
    async def test_guild_not_in_cache_returns_early(self):
        """bot.get_guild returns None - should log warn and return without creating channel"""
        mock_guild_cfg = MagicMock()
        mock_guild_cfg.id = test_guild

        with (
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            mock_bot.get_guild.return_value = None
            mock_config.primary.return_value = mock_guild_cfg

            await ensure_eggs_ready()

        mock_bot.get_guild.assert_called_once_with(test_guild)


# ============================================================
# additional get_or_create_user_thread() coverage
# ============================================================


class TestGetOrCreateUserThreadExtra:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_user_repo = AsyncMock()
        with (
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_config = mock_config
            yield

    async def test_no_user_doc_creates_thread(self):
        """user has no doc at all - creates thread and stores new EggUserDocument"""
        from doom_bot.eggs.hatching import get_or_create_user_thread

        self.egg_user_repo.get.return_value = None

        mock_thread = MagicMock()
        mock_thread.id = 8888888888
        mock_eggs_channel = MagicMock()
        mock_eggs_channel.create_thread = AsyncMock(return_value=mock_thread)

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = 4444444444
        self.mock_config.guild.return_value = mock_guild_cfg
        self.mock_bot.get_channel.return_value = mock_eggs_channel

        result = await get_or_create_user_thread(test_guild, test_user, 'testuser')

        assert result is mock_thread
        self.egg_user_repo.upsert.assert_called_once()
        upserted = self.egg_user_repo.upsert.call_args.args[0]
        assert isinstance(upserted, EggUserDocument)
        assert upserted.thread_id == mock_thread.id

    async def test_zero_thread_id_falls_through_to_create(self):
        """user_doc exists but thread_id == 0 (falsy) - falls through to create a new thread"""
        from doom_bot.eggs.hatching import get_or_create_user_thread

        user_doc = _make_user_doc(thread_id=0)
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_thread.id = 7777777777
        mock_eggs_channel = MagicMock()
        mock_eggs_channel.create_thread = AsyncMock(return_value=mock_thread)

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = 4444444444
        self.mock_config.guild.return_value = mock_guild_cfg
        self.mock_bot.get_channel.return_value = mock_eggs_channel

        result = await get_or_create_user_thread(test_guild, test_user, 'testuser')

        assert result is mock_thread
        self.egg_user_repo.upsert.assert_called_once()

    async def test_no_eggs_channel_raises(self):
        """eggs channel not in bot cache - raises RuntimeError"""
        from doom_bot.eggs.hatching import get_or_create_user_thread

        self.egg_user_repo.get.return_value = None

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = 4444444444
        self.mock_config.guild.return_value = mock_guild_cfg
        self.mock_bot.get_channel.return_value = None  # channel not in cache

        with pytest.raises(RuntimeError):
            await get_or_create_user_thread(test_guild, test_user, 'testuser')


# ============================================================
# additional hatch_egg() guard coverage
# ============================================================


class TestHatchEggGuards:
    @pytest.fixture(autouse=True)
    def setup_repos(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()
        hatching_mod._hatch_last_used.clear()

        with (
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
            patch('doom_bot.eggs.hatching.bot') as mock_bot,
            patch('doom_bot.eggs.hatching.config') as mock_config,
        ):
            mock_config.hatch.tuning.hatch_cooldown_seconds = 5
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            yield

    async def test_no_user_doc_raises(self):
        """user_doc is None after finding a ready egg - raises RuntimeError"""
        egg = _make_egg(hatches_at=100, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        self.egg_user_repo.get.return_value = None

        with pytest.raises(RuntimeError, match='no egg thread found for user'):
            await hatch_egg(test_guild, test_user)

    async def test_zero_thread_id_raises(self):
        """user_doc exists but thread_id == 0 - raises RuntimeError"""
        egg = _make_egg(hatches_at=100, result='🐣')
        self.egg_repo.get_oldest_ready.return_value = egg
        user_doc = _make_user_doc(thread_id=0)
        self.egg_user_repo.get.return_value = user_doc

        with pytest.raises(RuntimeError, match='no egg thread found for user'):
            await hatch_egg(test_guild, test_user)

    async def test_no_result_raises(self):
        """egg.result is None - raises RuntimeError before animation starts"""
        egg = _make_egg(hatches_at=100, result=None)  # pyright: ignore[reportArgumentType]
        self.egg_repo.get_oldest_ready.return_value = egg

        user_doc = _make_user_doc()
        self.egg_user_repo.get.return_value = user_doc

        mock_thread = MagicMock()
        mock_msg = AsyncMock()
        mock_msg.jump_url = f'https://discord.com/channels/{test_guild}/{test_thread}/{test_message}'
        mock_thread.get_partial_message = MagicMock(return_value=mock_msg)
        self.mock_bot.get_channel.return_value = mock_thread

        with pytest.raises(RuntimeError, match='no result set'):
            await hatch_egg(test_guild, test_user)


# ============================================================
# additional run_hatch_animation() coverage
# ============================================================


class TestRunHatchAnimationExtra:
    async def test_presence_update_triggered(self):
        """scheduler.add_job is called once after the animation completes"""
        mock_message = MagicMock()
        mock_message.edit = AsyncMock()
        hatching_mod._last_presence_update = 0.0

        with (
            patch('doom_bot.eggs.hatching.asyncio') as mock_asyncio,
            patch('doom_bot.eggs.hatching.config') as mock_config,
            patch.object(real_scheduler, 'add_job') as mock_add_job,
        ):
            mock_asyncio.sleep = AsyncMock()
            mock_config.hatch.tuning.animation_wait_min = 10
            mock_config.hatch.tuning.animation_wait_max = 15
            await run_hatch_animation(mock_message, '🐣', 'common')

        mock_add_job.assert_called_once()


# ============================================================
# ensure_progress_emojis()
# ============================================================


class TestEnsureProgressEmojis:
    async def test_creates_all_missing(self):
        """guild has no emojis - all 6 progress bar emojis are created"""
        mock_emoji = MagicMock()
        mock_guild = MagicMock()
        mock_guild.emojis = []
        mock_guild.id = test_guild
        mock_guild.create_custom_emoji = AsyncMock(return_value=mock_emoji)

        with patch('pathlib.Path.read_bytes', return_value=b'fakepng'):
            from doom_bot.eggs.emojis import ensure_progress_emojis

            result = await ensure_progress_emojis(mock_guild)

        assert len(result) == 6
        assert mock_guild.create_custom_emoji.call_count == 6

    async def test_reuses_existing(self):
        """all 6 progress emojis already on guild - create_custom_emoji never called"""
        from doom_bot.eggs.emojis import _progress_segments

        existing = [MagicMock(name=f'progress_{seg}') for seg in _progress_segments]
        for e, seg in zip(existing, _progress_segments):
            e.name = f'progress_{seg}'

        mock_guild = MagicMock()
        mock_guild.emojis = existing
        mock_guild.id = test_guild
        mock_guild.create_custom_emoji = AsyncMock()

        from doom_bot.eggs.emojis import ensure_progress_emojis

        result = await ensure_progress_emojis(mock_guild)

        assert len(result) == 6
        mock_guild.create_custom_emoji.assert_not_called()


# ============================================================
# render_progress_bar()
# ============================================================


def _progress_emojis_dict() -> dict[str, int]:
    return {
        'left_full': 1001,
        'left_empty': 1002,
        'none_full': 1003,
        'none_empty': 1004,
        'right_full': 1005,
        'right_empty': 1006,
    }


class TestRenderProgressBar:
    def test_with_emoji_ids(self):
        """all progress_emojis configured - output uses <:pb:id> format"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = _progress_emojis_dict()
            from doom_bot.eggs.emojis import render_progress_bar

            result = render_progress_bar(5, 10)

        assert '<:pb:' in result

    def test_without_emoji_ids_falls_back(self):
        """progress_emojis empty - falls back to unicode block characters"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = {}
            from doom_bot.eggs.emojis import render_progress_bar

            result = render_progress_bar(5, 10)

        assert '<:pb:' not in result
        assert '■' in result or '□' in result

    def test_zero_filled(self):
        """filled=0 - all 10 segments are empty"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = {}
            from doom_bot.eggs.emojis import render_progress_bar

            result = render_progress_bar(0, 10)

        assert '■' not in result
        assert result.count('□') == 10

    def test_fully_filled(self):
        """filled=total - all 10 segments are full"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = {}
            from doom_bot.eggs.emojis import render_progress_bar

            result = render_progress_bar(10, 10)

        assert '□' not in result
        assert result.count('■') == 10

    def test_zero_total_no_division_error(self):
        """total=0 - guard prevents division by zero; all segments empty"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = {}
            from doom_bot.eggs.emojis import render_progress_bar

            result = render_progress_bar(5, 0)

        assert '■' not in result

    def test_partial_fill(self):
        """filled=5, total=10 - exactly half filled segments"""
        with patch('doom_bot.client.core.config') as mock_config:
            mock_config.theme.progress_emojis = {}
            from doom_bot.eggs.emojis import render_progress_bar

            # segments=10: units=round(5/10*10)=5
            # left=full (5>=1), middles i=0..7: full if 5>=i+2 -> i<=3 (4 full, 4 empty)
            # right=empty (5!=10)
            # total: 1+4=5 full, 4+1=5 empty
            result = render_progress_bar(5, 10)

        assert result.count('■') == 5
        assert result.count('□') == 5


# ============================================================
# EggCleanupTask
# ============================================================


class TestEggCleanupTask:
    @pytest.fixture(autouse=True)
    def setup(self):
        mock_egg_repo = AsyncMock()
        mock_egg_user_repo = AsyncMock()

        with (
            patch('doom_bot.tasks.egg_cleanup.bot') as mock_bot,
            patch('doom_bot.tasks.egg_cleanup.config') as mock_config,
            patch.object(hatching_mod, '_egg_repo', mock_egg_repo),
            patch.object(hatching_mod, '_egg_user_repo', mock_egg_user_repo),
        ):
            mock_config.primary.return_value = MagicMock(id=test_guild)
            mock_config.hatch.tuning.cleanup_cutoff_hours = 12
            self.mock_bot = mock_bot
            self.mock_config = mock_config
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            yield

    async def test_guild_not_in_cache_skips(self):
        """guild not in bot cache - returns without listing users"""
        self.mock_bot.get_guild.return_value = None
        await egg_cleanup_task.run()
        self.egg_user_repo.list_all.assert_not_called()

    async def test_deletes_non_egg_messages(self):
        """message not in egg_message_ids older than 12h is deleted"""
        import datetime as dt

        cutoff_dt = dt.datetime(2026, 4, 5, 15, 0, 0, tzinfo=dt.UTC)
        old_created_at = dt.datetime(2026, 4, 5, 0, 0, 0)  # naive utc, 15h before cutoff

        with patch('doom_bot.tasks.egg_cleanup.datetime') as mock_dt:
            mock_dt.now.return_value = cutoff_dt

            mock_guild = MagicMock()
            self.mock_bot.get_guild.return_value = mock_guild

            user_doc = _make_user_doc(thread_id=test_thread)
            self.egg_user_repo.list_all = AsyncMock(return_value=[user_doc])
            self.egg_repo.list_unhatched = AsyncMock(return_value=[])
            self.egg_repo.list_hatched = AsyncMock(return_value=[])

            # message older than cutoff, not an egg message
            mock_msg = AsyncMock()
            mock_msg.id = 999999999
            mock_msg.created_at = old_created_at
            mock_msg.reactions = []

            mock_thread = MagicMock()

            async def fake_history(**kwargs):
                yield mock_msg

            mock_thread.history = fake_history
            self.mock_bot.get_channel.return_value = mock_thread

            await egg_cleanup_task.run()

        mock_msg.delete.assert_called_once()

    async def test_skips_egg_messages(self):
        """message whose id matches a known egg - not deleted"""
        import datetime as dt

        cutoff_dt = dt.datetime(2026, 4, 5, 15, 0, 0, tzinfo=dt.UTC)
        old_created_at = dt.datetime(2026, 4, 5, 0, 0, 0)

        with patch('doom_bot.tasks.egg_cleanup.datetime') as mock_dt:
            mock_dt.now.return_value = cutoff_dt

            mock_guild = MagicMock()
            self.mock_bot.get_guild.return_value = mock_guild

            user_doc = _make_user_doc(thread_id=test_thread)
            self.egg_user_repo.list_all = AsyncMock(return_value=[user_doc])

            # the message id matches a tracked egg
            egg = _make_egg(message_id=test_message)
            self.egg_repo.list_unhatched = AsyncMock(return_value=[egg])
            self.egg_repo.list_hatched = AsyncMock(return_value=[])

            mock_msg = AsyncMock()
            mock_msg.id = test_message  # known egg message
            mock_msg.created_at = old_created_at

            mock_thread = MagicMock()

            async def fake_history(**kwargs):
                yield mock_msg

            mock_thread.history = fake_history
            self.mock_bot.get_channel.return_value = mock_thread

            await egg_cleanup_task.run()

        mock_msg.delete.assert_not_called()

    async def test_thread_not_found_skips_user(self):
        """fetch_channel raises NotFound - user is skipped without error"""
        import datetime as dt

        cutoff_dt = dt.datetime(2026, 4, 5, 15, 0, 0, tzinfo=dt.UTC)

        with patch('doom_bot.tasks.egg_cleanup.datetime') as mock_dt:
            mock_dt.now.return_value = cutoff_dt

            mock_guild = MagicMock()
            mock_guild.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
            self.mock_bot.get_guild.return_value = mock_guild
            self.mock_bot.get_channel.return_value = None  # not in cache

            user_doc = _make_user_doc(thread_id=test_thread)
            self.egg_user_repo.list_all = AsyncMock(return_value=[user_doc])

            await egg_cleanup_task.run()

        # no eggs queried since we skipped the user
        self.egg_repo.list_unhatched.assert_not_called()
