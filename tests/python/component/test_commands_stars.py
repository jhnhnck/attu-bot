"""
AttuBot - Stars Command Integration Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests stars commands with real StarboardRepository + MessageRepository state.
Discord gateway objects (bot, channel, message) are faked; leaderboard aggregation
and random selection run against actual MongoDB.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from attubot.database.models import MessageAuthor, MessageContent, MessageDocument, StarredMessageDocument
from attubot.database.repositories import MessageRepository, StarboardRepository


pytestmark = pytest.mark.component

TEST_GUILD = 1234567890
SB_CHANNEL = 4000000001
MSG_CHANNEL = 4000000002

# author ids for seeding
AUTHOR_A = 100000001
AUTHOR_B = 100000002
AUTHOR_C = 100000003

# reactor ids
USER_1 = 200000001
USER_2 = 200000002
USER_3 = 200000003


def _sb_doc(message_id: int, author_id: int, reactions: dict | None = None, starboard_message_id: int | None = None, total_reactions: int = 0) -> StarredMessageDocument:
    r = reactions or {}
    total = total_reactions or sum(len(v) for v in r.values())
    return StarredMessageDocument(
        message_id=message_id,
        channel_id=MSG_CHANNEL,
        guild_id=TEST_GUILD,
        author_id=author_id,
        reactions=r,
        total_reactions=total,
        starboard_message_id=starboard_message_id,
    )


def _msg_doc(message_id: int, author_id: int = AUTHOR_A) -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=TEST_GUILD,
        channel_id=MSG_CHANNEL,
        author=MessageAuthor(id=author_id, name='testuser'),
        content=MessageContent(text=f'message {message_id}'),
        created_at=1704067200,
    )


@pytest_asyncio.fixture
async def stars_repos(component_db, make_guild):
    """set up real sb + msg repos and wire them into the module singletons for each test"""
    sb_repo = StarboardRepository(component_db)
    await sb_repo.init_indexes()
    msg_repo = MessageRepository(component_db)
    await msg_repo.init_indexes()

    cfg = make_guild(guild_id=TEST_GUILD)
    cfg.starboard.channel_id = SB_CHANNEL
    cfg.starboard.emojis = {'⭐': '#EEDD20'}

    import attubot.client.messages as _messages
    import attubot.client.starboard as _starboard

    _starboard._starboard_repo = sb_repo
    _messages._message_repo = msg_repo

    yield {'sb': sb_repo, 'msg': msg_repo, 'cfg': cfg}

    _starboard._starboard_repo = None
    _messages._message_repo = None


class TestStarsLeaderboards:
    async def test_most_stars_embed_ranks_by_stars_received(self, stars_repos, mock_ctx_factory):
        """most-stars orders authors by total reactions received on their messages"""
        sb = stars_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        # author A has 3 stars, B has 2, C has 1
        await sb.upsert(_sb_doc(1001, AUTHOR_A, {'⭐': [USER_1, USER_2, USER_3]}))
        await sb.upsert(_sb_doc(1002, AUTHOR_B, {'⭐': [USER_1, USER_2]}))
        await sb.upsert(_sb_doc(1003, AUTHOR_C, {'⭐': [USER_1]}))

        from attubot.commands.stars import stars_most_stars

        await stars_most_stars(ctx)

        assert len(ctx._responses) == 1
        embed = ctx._responses[0]['kwargs']['embed']
        desc = embed.description

        # A (3 stars) should appear before B (2 stars) and C (1 star)
        assert f'<@{AUTHOR_A}>' in desc
        assert f'<@{AUTHOR_B}>' in desc
        assert desc.index(f'<@{AUTHOR_A}>') < desc.index(f'<@{AUTHOR_B}>')
        assert desc.index(f'<@{AUTHOR_B}>') < desc.index(f'<@{AUTHOR_C}>')

    async def test_most_starred_embed_ranks_by_message_count(self, stars_repos, mock_ctx_factory):
        """most-starred counts messages that reached the starboard (have a starboard_message_id)"""
        sb = stars_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        # author A has 2 starboarded messages, B has 1
        await sb.upsert(_sb_doc(2001, AUTHOR_A, {'⭐': [USER_1]}, starboard_message_id=9001))
        await sb.upsert(_sb_doc(2002, AUTHOR_A, {'⭐': [USER_2]}, starboard_message_id=9002))
        await sb.upsert(_sb_doc(2003, AUTHOR_B, {'⭐': [USER_1]}, starboard_message_id=9003))
        # this one has no starboard post - excluded from count
        await sb.upsert(_sb_doc(2004, AUTHOR_B, {'⭐': [USER_1]}, starboard_message_id=None))

        from attubot.commands.stars import stars_most_starred

        await stars_most_starred(ctx)

        embed = ctx._responses[0]['kwargs']['embed']
        desc = embed.description
        assert desc.index(f'<@{AUTHOR_A}>') < desc.index(f'<@{AUTHOR_B}>')

    async def test_most_given_embed_ranks_by_stars_given(self, stars_repos, mock_ctx_factory):
        """most-given counts how many stars each user has given across all messages"""
        sb = stars_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        # USER_1 gives 3 stars total (2 on msg 3001, 1 on msg 3002)
        await sb.upsert(_sb_doc(3001, AUTHOR_A, {'⭐': [USER_1, USER_2]}))
        await sb.upsert(_sb_doc(3002, AUTHOR_A, {'⭐': [USER_1, USER_3]}))

        from attubot.commands.stars import stars_most_given

        await stars_most_given(ctx)

        embed = ctx._responses[0]['kwargs']['embed']
        desc = embed.description
        # USER_1 gave 2 stars, USER_2 and USER_3 each gave 1
        assert f'<@{USER_1}>' in desc
        assert desc.index(f'<@{USER_1}>') < desc.index(f'<@{USER_2}>')

    async def test_most_stars_responds_ephemeral_when_empty(self, stars_repos, mock_ctx_factory):
        """most-stars responds with 'no data yet' when there are no starred messages"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        from attubot.commands.stars import stars_most_stars

        await stars_most_stars(ctx)

        assert len(ctx._responses) == 1
        assert 'no data yet' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_most_starred_responds_ephemeral_when_empty(self, stars_repos, mock_ctx_factory):
        """most-starred responds with 'no data yet' when no messages have a starboard post"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        from attubot.commands.stars import stars_most_starred

        await stars_most_starred(ctx)

        assert len(ctx._responses) == 1
        assert 'no data yet' in ctx._responses[0]['args'][0]

    async def test_most_given_responds_ephemeral_when_empty(self, stars_repos, mock_ctx_factory):
        """most-given responds with 'no data yet' when there are no starred messages"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        from attubot.commands.stars import stars_most_given

        await stars_most_given(ctx)

        assert len(ctx._responses) == 1
        assert 'no data yet' in ctx._responses[0]['args'][0]


class TestStarsRandom:
    async def test_random_returns_message_with_multiple_stars(self, stars_repos, mock_ctx_factory):
        """stars random returns a message with >= 2 total reactions"""
        sb = stars_repos['sb']
        msg_repo = stars_repos['msg']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        await sb.upsert(_sb_doc(5001, AUTHOR_A, {'⭐': [USER_1, USER_2]}, total_reactions=2))
        await msg_repo.upsert(_msg_doc(5001))

        from attubot.commands.stars import stars_random

        with patch('attubot.client.starboard.build_embeds', new=AsyncMock(return_value=[])):
            await stars_random(ctx)

        assert len(ctx._responses) == 1
        content = ctx._responses[0]['kwargs'].get('content', '')
        assert '5001' in content

    async def test_random_no_match_responds_no_messages(self, stars_repos, mock_ctx_factory):
        """stars random responds ephemeral when no messages with >= 2 stars exist"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)
        # repo is empty

        from attubot.commands.stars import stars_random

        await stars_random(ctx)

        assert len(ctx._responses) == 1
        assert 'no messages found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_lost_returns_message_with_exactly_one_star(self, stars_repos, mock_ctx_factory):
        """stars lost returns a message with exactly 1 total reaction"""
        sb = stars_repos['sb']
        msg_repo = stars_repos['msg']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        # doc with 1 star - matches lost (min=1, max=1)
        await sb.upsert(_sb_doc(6001, AUTHOR_A, {'⭐': [USER_1]}, total_reactions=1))
        await msg_repo.upsert(_msg_doc(6001))

        # doc with 3 stars - should not be returned by lost
        await sb.upsert(_sb_doc(6002, AUTHOR_B, {'⭐': [USER_1, USER_2, USER_3]}, total_reactions=3))
        await msg_repo.upsert(_msg_doc(6002, AUTHOR_B))

        from attubot.commands.stars import stars_lost

        with patch('attubot.client.starboard.build_embeds', new=AsyncMock(return_value=[])):
            await stars_lost(ctx)

        assert len(ctx._responses) == 1
        content = ctx._responses[0]['kwargs'].get('content', '')
        assert '6001' in content
        assert '6002' not in content

    async def test_random_no_match_when_only_one_star_messages(self, stars_repos, mock_ctx_factory):
        """stars random with min=2 returns no match when only 1-star messages exist"""
        sb = stars_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        await sb.upsert(_sb_doc(7001, AUTHOR_A, {'⭐': [USER_1]}, total_reactions=1))

        from attubot.commands.stars import stars_random

        await stars_random(ctx)

        assert 'no messages found' in ctx._responses[0]['args'][0]


class TestStarsRecheck:
    async def test_recheck_stores_message_and_calls_backfill(self, stars_repos, mock_ctx_factory):
        """recheck fetches the message, stores it in the repo, and calls backfill_message_reactions"""
        msg_repo = stars_repos['msg']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        message_id = 8001
        message_link = f'https://discord.com/channels/{TEST_GUILD}/{MSG_CHANNEL}/{message_id}'

        fake_discord_msg = MagicMock()
        fake_discord_msg.id = message_id
        fake_channel = MagicMock()
        fake_channel.fetch_message = AsyncMock(return_value=fake_discord_msg)

        stored_doc = _msg_doc(message_id)

        with (
            patch('attubot.bot') as mock_bot,
            patch('attubot.client.messages.build_message_doc', new=AsyncMock(return_value=stored_doc)),
            patch('attubot.client.starboard.backfill_message_reactions', new=AsyncMock()) as mock_backfill,
        ):
            mock_bot.get_channel.return_value = fake_channel

            from attubot.commands.stars import stars_recheck

            await stars_recheck(ctx, message_link=message_link)

        # verify the response
        assert any('recheck complete' in (r['args'][0] if r['args'] else '') for r in ctx._responses)

        # message should be in the DB
        assert await msg_repo.get(message_id) is not None

        # backfill should have been invoked with the fetched message
        mock_backfill.assert_called_once_with(fake_discord_msg, TEST_GUILD)

    async def test_recheck_rejects_invalid_link(self, stars_repos, mock_ctx_factory):
        """recheck responds ephemeral when given a non-discord message link"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        from attubot.commands.stars import stars_recheck

        await stars_recheck(ctx, message_link='not-a-link')

        assert ctx._responses[0]['kwargs'].get('ephemeral') is True
        assert 'invalid message link' in ctx._responses[0]['args'][0]

    async def test_recheck_rejects_wrong_guild_link(self, stars_repos, mock_ctx_factory):
        """recheck responds ephemeral when the message link is from a different guild"""
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)
        other_guild = 9999999999
        message_link = f'https://discord.com/channels/{other_guild}/{MSG_CHANNEL}/8002'

        from attubot.commands.stars import stars_recheck

        await stars_recheck(ctx, message_link=message_link)

        assert ctx._responses[0]['kwargs'].get('ephemeral') is True
        assert 'different server' in ctx._responses[0]['args'][0]
