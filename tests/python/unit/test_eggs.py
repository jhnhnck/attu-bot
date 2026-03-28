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

import pytest

import attubot.eggs.hatching as hatching_mod
from attubot.database.models import EggDocument, EggUserDocument
from attubot.eggs.hatching import (
    collect_egg,
    ensure_eggs_ready,
    hatch_date,
    hatch_egg,
    run_hatch_animation,
)


# ---- constants ----

TEST_GUILD = 1234567890
TEST_USER = 9876543210
TEST_USER2 = 1111111111
TEST_THREAD = 5555555555
TEST_MESSAGE = 222222222222


# ---- helpers ----


def _make_egg(*, hatched=False, hatches_at=0.0, message_id=TEST_MESSAGE, rarity='common', result='🐣'):
    return EggDocument(
        egg_id='test-egg-id',
        guild_id=TEST_GUILD,
        user_id=TEST_USER,
        rarity=rarity,
        collected_at=1000.0,
        hatches_at=hatches_at,
        hatched=hatched,
        result=result,
        message_id=message_id,
    )


def _make_user_doc(*, thread_id=TEST_THREAD, last_collected_at=0.0):
    return EggUserDocument(
        guild_id=TEST_GUILD,
        user_id=TEST_USER,
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
        mock_msg.jump_url = f'https://discord.com/channels/{TEST_GUILD}/{TEST_THREAD}/{TEST_MESSAGE}'
        mock_thread.send = AsyncMock(return_value=mock_msg)
        mock_thread.id = TEST_THREAD

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
        mock_guild_cfg.channels.eggs = TEST_THREAD

        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg

            result = await collect_egg(TEST_GUILD, TEST_USER, 'testuser')

        assert isinstance(result, str)
        assert 'discord.com' in result
        self.egg_repo.insert.assert_called_once()
        # upsert called twice for new user: once in get_or_create_user_thread, once to update cooldown
        assert self.egg_user_repo.upsert.call_count == 2

    async def test_cooldown_active_raises(self):
        """user collected 60s ago - still within 900s cooldown"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=time.time() - 60)

        with pytest.raises(ValueError, match='try again in'):
            await collect_egg(TEST_GUILD, TEST_USER, 'testuser')

    async def test_cooldown_expired_succeeds(self):
        """user collected 1000s ago - cooldown has elapsed"""
        self.egg_user_repo.get.return_value = _make_user_doc(last_collected_at=time.time() - 1000)
        self.egg_user_repo.upsert.return_value = None
        self.egg_repo.insert.return_value = None

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.channels.eggs = TEST_THREAD

        with patch('attubot.eggs.hatching.config') as mock_config:
            mock_config.guild.return_value = mock_guild_cfg

            result = await collect_egg(TEST_GUILD, TEST_USER, 'testuser')

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
            patch('attubot.eggs.hatching.asyncio') as mock_asyncio,
        ):
            self.egg_repo = mock_egg_repo
            self.egg_user_repo = mock_egg_user_repo
            self.mock_bot = mock_bot
            self.mock_asyncio = mock_asyncio
            yield

    async def test_no_eggs(self):
        self.egg_repo.get_oldest_ready.return_value = None
        self.egg_repo.get_next_unhatched.return_value = None

        result, ts = await hatch_egg(TEST_GUILD, TEST_USER)

        assert result == 'no_eggs'
        assert ts is None

    async def test_egg_not_ready(self):
        self.egg_repo.get_oldest_ready.return_value = None
        next_egg = _make_egg(hatches_at=9999.0)
        self.egg_repo.get_next_unhatched.return_value = next_egg

        result, ts = await hatch_egg(TEST_GUILD, TEST_USER)

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
        mock_msg.jump_url = f'https://discord.com/channels/{TEST_GUILD}/{TEST_THREAD}/{TEST_MESSAGE}'
        mock_thread.fetch_message = AsyncMock(return_value=mock_msg)
        self.mock_bot.get_channel.return_value = mock_thread

        result, ts = await hatch_egg(TEST_GUILD, TEST_USER)

        assert 'discord.com' in result
        assert ts is None
        self.egg_repo.mark_hatched.assert_called_once_with(egg.egg_id, egg.result)
        self.mock_asyncio.create_task.assert_called_once()


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
        mock_guild_cfg.id = TEST_GUILD
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
        mock_config_repo.update_guild_field.assert_called_once_with(TEST_GUILD, 'channels.eggs', mock_channel.id)

    async def test_skips_if_channel_exists(self):
        """channels.eggs already set - should not create another channel"""
        mock_discord_guild = MagicMock()
        mock_discord_guild.create_text_channel = AsyncMock()

        mock_guild_cfg = MagicMock()
        mock_guild_cfg.id = TEST_GUILD
        mock_guild_cfg.channels.eggs = 12345

        with (
            patch('attubot.eggs.hatching.bot') as mock_bot,
            patch('attubot.eggs.hatching.config') as mock_config,
        ):
            mock_bot.get_guild.return_value = mock_discord_guild
            mock_config.primary.return_value = mock_guild_cfg

            await ensure_eggs_ready()

        mock_discord_guild.create_text_channel.assert_not_called()
