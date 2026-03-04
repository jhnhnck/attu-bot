"""
AttuBot - MessageBackfillTask Component Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests channel filtering and persistence behavior with a real MessageRepository and
fake Discord guild/channel objects. `build_message_doc` is patched to avoid needing
real discord.Message attributes - the focus is on channel selection and cursor logic.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot import config
from attubot.database.models import MessageDocument
from attubot.database.repositories import MessageRepository


pytestmark = pytest.mark.component

TEST_GUILD = 1234567890
CH_READABLE = 2000000001
CH_READABLE_2 = 2000000002
CH_LOGS = 2000000003


def _fake_msg(message_id: int, channel_id: int, guild_id: int = TEST_GUILD) -> MagicMock:
    msg = MagicMock()
    msg.id = message_id
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    return msg


def _fake_channel(channel_id: int, readable: bool = True) -> MagicMock:
    ch = MagicMock()
    ch.id = channel_id
    ch.name = f'channel-{channel_id}'
    perms = MagicMock()
    perms.read_message_history = readable
    ch.permissions_for = MagicMock(return_value=perms)
    return ch


def _as_history(*messages):
    """return a factory that produces a fresh async generator for each call to channel.history()"""

    def _factory(**kwargs):
        async def _gen():
            for msg in messages:
                yield msg

        return _gen()

    return MagicMock(side_effect=_factory)


def _capturing_history(messages, captured: list):
    """like _as_history but records the kwargs each call is made with"""

    def _factory(**kwargs):
        captured.append(kwargs)

        async def _gen():
            for msg in messages:
                yield msg

        return _gen()

    return MagicMock(side_effect=_factory)


def _doc_for(message_id: int, channel_id: int) -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=TEST_GUILD,
        channel_id=channel_id,
        author_id=111,
        author_name='testuser',
        content=f'message {message_id}',
        created_at=1704067200,
    )


class TestBackfillChannel:
    async def test_stores_messages_from_channel_in_db(self, component_db, make_guild):
        """_backfill_channel persists messages returned by channel.history to the repo"""
        msg_repo = MessageRepository(component_db)
        await msg_repo.init_indexes()

        make_guild(guild_id=TEST_GUILD)

        ch = _fake_channel(CH_READABLE)
        ch.history = _as_history(
            _fake_msg(101, CH_READABLE),
            _fake_msg(102, CH_READABLE),
            _fake_msg(103, CH_READABLE),
        )

        import attubot.messages as _messages

        _messages._message_repo = msg_repo
        try:
            with patch('attubot.tasks.message_backfill.build_message_doc', new=AsyncMock(side_effect=lambda m: _doc_for(m.id, m.channel.id))):
                from attubot.tasks.message_backfill import MessageBackfillTask

                count = await MessageBackfillTask()._backfill_channel(TEST_GUILD, ch)

            assert count == 3
            assert await msg_repo.count_for_channel(TEST_GUILD, CH_READABLE) == 3
        finally:
            _messages._message_repo = None

    async def test_uses_cursor_after_latest_stored_message(self, component_db, make_guild):
        """_backfill_channel passes after=Object(id=latest) when prior messages exist in DB"""
        msg_repo = MessageRepository(component_db)
        await msg_repo.init_indexes()

        make_guild(guild_id=TEST_GUILD)

        # seed message 100 so get_latest_in_channel returns 100
        await msg_repo.upsert(_doc_for(100, CH_READABLE))

        new_messages = [_fake_msg(101, CH_READABLE), _fake_msg(102, CH_READABLE)]
        history_calls: list = []

        ch = _fake_channel(CH_READABLE)
        ch.history = _capturing_history(new_messages, history_calls)

        import attubot.messages as _messages

        _messages._message_repo = msg_repo
        try:
            with patch('attubot.tasks.message_backfill.build_message_doc', new=AsyncMock(side_effect=lambda m: _doc_for(m.id, m.channel.id))):
                from attubot.tasks.message_backfill import MessageBackfillTask

                count = await MessageBackfillTask()._backfill_channel(TEST_GUILD, ch)

            assert count == 2
            assert len(history_calls) == 1
            assert history_calls[0]['after'].id == 100
            # 1 pre-existing + 2 new
            assert await msg_repo.count_for_channel(TEST_GUILD, CH_READABLE) == 3
        finally:
            _messages._message_repo = None

    async def test_fetches_full_history_when_channel_has_no_prior_messages(self, component_db, make_guild):
        """_backfill_channel calls history() without an after= cursor when the channel is empty in DB"""
        msg_repo = MessageRepository(component_db)
        await msg_repo.init_indexes()

        make_guild(guild_id=TEST_GUILD)

        history_calls: list = []
        ch = _fake_channel(CH_READABLE)
        ch.history = _capturing_history([_fake_msg(200, CH_READABLE)], history_calls)

        import attubot.messages as _messages

        _messages._message_repo = msg_repo
        try:
            with patch('attubot.tasks.message_backfill.build_message_doc', new=AsyncMock(side_effect=lambda m: _doc_for(m.id, m.channel.id))):
                from attubot.tasks.message_backfill import MessageBackfillTask

                await MessageBackfillTask()._backfill_channel(TEST_GUILD, ch)

            assert 'after' not in history_calls[0]
        finally:
            _messages._message_repo = None

    async def test_returns_zero_on_permission_error(self, component_db, make_guild):
        """_backfill_channel returns 0 and does not raise when discord raises Forbidden"""
        import discord

        msg_repo = MessageRepository(component_db)
        await msg_repo.init_indexes()

        make_guild(guild_id=TEST_GUILD)

        ch = _fake_channel(CH_READABLE)

        async def _forbidden_gen():
            raise discord.Forbidden(MagicMock(), 'missing permissions')
            # unreachable - just to make it an async generator
            yield

        ch.history = MagicMock(return_value=_forbidden_gen())

        import attubot.messages as _messages

        _messages._message_repo = msg_repo
        try:
            with patch('attubot.tasks.message_backfill.build_message_doc', new=AsyncMock()):
                from attubot.tasks.message_backfill import MessageBackfillTask

                count = await MessageBackfillTask()._backfill_channel(TEST_GUILD, ch)

            assert count == 0
        finally:
            _messages._message_repo = None


class TestRunChannelFiltering:
    async def test_run_processes_channels_from_collect(self, component_db, make_guild):
        """run() calls _backfill_channel for each channel returned by _collect_channels"""
        msg_repo = MessageRepository(component_db)
        await msg_repo.init_indexes()

        make_guild(guild_id=TEST_GUILD)

        ch1 = _fake_channel(CH_READABLE)
        ch1.history = _as_history(_fake_msg(301, CH_READABLE), _fake_msg(302, CH_READABLE))
        ch2 = _fake_channel(CH_READABLE_2)
        ch2.history = _as_history(_fake_msg(303, CH_READABLE_2))

        fake_guild = MagicMock()
        fake_guild.id = TEST_GUILD
        fake_guild.me = MagicMock()

        import attubot.messages as _messages

        _messages._message_repo = msg_repo
        try:
            with (
                patch('attubot.tasks.message_backfill.bot') as mock_bot,
                patch('attubot.tasks.message_backfill.build_message_doc', new=AsyncMock(side_effect=lambda m: _doc_for(m.id, m.channel.id))),
                patch('attubot.tasks.message_backfill.MessageBackfillTask._collect_channels', new=AsyncMock(return_value=[ch1, ch2])),
            ):
                mock_bot.get_guild.return_value = fake_guild
                from attubot.tasks.message_backfill import MessageBackfillTask

                await MessageBackfillTask().run()

            assert await msg_repo.count_for_channel(TEST_GUILD, CH_READABLE) == 2
            assert await msg_repo.count_for_channel(TEST_GUILD, CH_READABLE_2) == 1
        finally:
            _messages._message_repo = None

    async def test_collect_channels_excludes_logs_channel(self, make_guild):
        """_collect_channels omits the logs channel from the returned list"""
        import discord

        make_guild(guild_id=TEST_GUILD)
        cfg = config.guild(TEST_GUILD)
        cfg.channels.logs = CH_LOGS

        me = MagicMock()
        logs_ch = MagicMock(spec=discord.TextChannel)
        logs_ch.id = CH_LOGS
        logs_ch.permissions_for = MagicMock(return_value=MagicMock(read_message_history=True))

        readable_ch = MagicMock(spec=discord.TextChannel)
        readable_ch.id = CH_READABLE
        readable_ch.permissions_for = MagicMock(return_value=MagicMock(read_message_history=True))

        fake_guild = MagicMock()
        fake_guild.channels = [logs_ch, readable_ch]
        fake_guild.active_threads = AsyncMock(return_value=[])

        from attubot.tasks.message_backfill import MessageBackfillTask

        channels = await MessageBackfillTask()._collect_channels(fake_guild, CH_LOGS, me)
        ids = [c.id for c in channels]

        assert CH_LOGS not in ids
        assert CH_READABLE in ids

    async def test_collect_channels_excludes_unreadable_channels(self, make_guild):
        """_collect_channels omits channels where read_message_history permission is False"""
        import discord

        make_guild(guild_id=TEST_GUILD)

        me = MagicMock()
        readable_ch = MagicMock(spec=discord.TextChannel)
        readable_ch.id = CH_READABLE
        readable_ch.permissions_for = MagicMock(return_value=MagicMock(read_message_history=True))

        unreadable_ch = MagicMock(spec=discord.TextChannel)
        unreadable_ch.id = CH_READABLE_2
        unreadable_ch.permissions_for = MagicMock(return_value=MagicMock(read_message_history=False))

        fake_guild = MagicMock()
        fake_guild.channels = [readable_ch, unreadable_ch]
        fake_guild.active_threads = AsyncMock(return_value=[])

        from attubot.tasks.message_backfill import MessageBackfillTask

        channels = await MessageBackfillTask()._collect_channels(fake_guild, 0, me)
        ids = [c.id for c in channels]

        assert CH_READABLE in ids
        assert CH_READABLE_2 not in ids

    async def test_collect_channels_includes_active_threads(self, make_guild):
        """_collect_channels includes readable active threads that are not children of logs"""
        import discord

        make_guild(guild_id=TEST_GUILD)
        cfg = config.guild(TEST_GUILD)
        cfg.channels.logs = CH_LOGS

        me = MagicMock()

        fake_thread = MagicMock(spec=discord.Thread)
        fake_thread.id = 3000000001
        fake_thread.parent_id = CH_READABLE  # not logs
        fake_thread.permissions_for = MagicMock(return_value=MagicMock(read_message_history=True))

        logs_thread = MagicMock(spec=discord.Thread)
        logs_thread.id = 3000000002
        logs_thread.parent_id = CH_LOGS  # child of logs - should be excluded
        logs_thread.permissions_for = MagicMock(return_value=MagicMock(read_message_history=True))

        fake_guild = MagicMock()
        fake_guild.channels = []
        fake_guild.active_threads = AsyncMock(return_value=[fake_thread, logs_thread])

        from attubot.tasks.message_backfill import MessageBackfillTask

        channels = await MessageBackfillTask()._collect_channels(fake_guild, CH_LOGS, me)
        ids = [c.id for c in channels]

        assert fake_thread.id in ids
        assert logs_thread.id not in ids

    async def test_run_skips_guild_not_in_bot_cache(self, make_guild):
        """run() skips a guild when bot.get_guild() returns None"""
        make_guild(guild_id=TEST_GUILD)

        with (
            patch('attubot.tasks.message_backfill.bot') as mock_bot,
            patch('attubot.tasks.message_backfill.MessageBackfillTask._collect_channels', new=AsyncMock()) as mock_collect,
        ):
            mock_bot.get_guild.return_value = None
            from attubot.tasks.message_backfill import MessageBackfillTask

            await MessageBackfillTask().run()

        mock_collect.assert_not_called()
