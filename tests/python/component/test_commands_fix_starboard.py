"""
AttuBot - Fix Starboard Command Component Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests the /fix starboard purge command with a real StarboardRepository against live MongoDB.
Discord gateway objects (bot, channel, message) are faked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
import pytest_asyncio

from attubot.database.models import StarredMessageDocument
from attubot.database.repositories import StarboardRepository


pytestmark = pytest.mark.component

TEST_GUILD = 1234567890
SB_CHANNEL = 4000000010
MSG_CHANNEL = 4000000011
AUTHOR_A = 100000010
USER_1 = 200000010

MSG_ID = 8881000001
SB_POST_ID = 8882000001


def _sb_doc(message_id: int, starboard_message_id: int | None = None) -> StarredMessageDocument:
    return StarredMessageDocument(
        message_id=message_id,
        channel_id=MSG_CHANNEL,
        guild_id=TEST_GUILD,
        author_id=AUTHOR_A,
        reactions={'⭐': [USER_1]},
        total_reactions=1,
        starboard_message_id=starboard_message_id,
    )


@pytest_asyncio.fixture
async def fix_sb_repos(component_db, make_guild):
    """set up real sb repo and wire it into the starboard module singleton"""
    sb_repo = StarboardRepository(component_db)
    await sb_repo.init_indexes()

    cfg = make_guild(guild_id=TEST_GUILD)
    cfg.starboard.channel_id = SB_CHANNEL
    cfg.starboard.emojis = {'⭐': '#EEDD20'}

    import attubot.client.starboard as _starboard

    _starboard._starboard_repo = sb_repo

    yield {'sb': sb_repo, 'cfg': cfg}

    _starboard._starboard_repo = None


class TestFixStarboardPurge:
    async def test_purge_removes_document_from_db(self, fix_sb_repos, mock_ctx_factory):
        """purge deletes the starred message document from the database"""
        sb = fix_sb_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        await sb.upsert(_sb_doc(MSG_ID))
        assert await sb.get(MSG_ID) is not None

        message_link = f'https://discord.com/channels/{TEST_GUILD}/{MSG_CHANNEL}/{MSG_ID}'

        from attubot.commands.fix import fix_starboard_purge

        await fix_starboard_purge(ctx, message_link=message_link)

        assert await sb.get(MSG_ID) is None
        assert len(ctx._responses) == 1
        assert f'{MSG_ID}' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is not True

    async def test_purge_also_deletes_discord_post(self, fix_sb_repos, mock_ctx_factory):
        """purge calls delete on the linked discord starboard post"""
        sb = fix_sb_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        await sb.upsert(_sb_doc(MSG_ID, starboard_message_id=SB_POST_ID))

        fake_msg = AsyncMock()
        fake_channel = AsyncMock()
        fake_channel.fetch_message = AsyncMock(return_value=fake_msg)

        message_link = f'https://discord.com/channels/{TEST_GUILD}/{MSG_CHANNEL}/{MSG_ID}'

        from attubot.commands.fix import fix_starboard_purge

        with patch('attubot.commands.fix.bot.get_channel', return_value=fake_channel):
            await fix_starboard_purge(ctx, message_link=message_link)

        fake_msg.delete.assert_called_once()
        assert await sb.get(MSG_ID) is None
        response = ctx._responses[0]['args'][0]
        assert 'deleted the starboard post' in response

    async def test_purge_handles_notfound_discord_post(self, fix_sb_repos, mock_ctx_factory):
        """purge still deletes the db entry when the discord post is already gone"""
        sb = fix_sb_repos['sb']
        ctx = mock_ctx_factory(guild_id=TEST_GUILD)

        await sb.upsert(_sb_doc(MSG_ID, starboard_message_id=SB_POST_ID))

        fake_channel = AsyncMock()
        fake_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))

        message_link = f'https://discord.com/channels/{TEST_GUILD}/{MSG_CHANNEL}/{MSG_ID}'

        from attubot.commands.fix import fix_starboard_purge

        with patch('attubot.commands.fix.bot.get_channel', return_value=fake_channel):
            await fix_starboard_purge(ctx, message_link=message_link)

        # doc still deleted despite discord.NotFound
        assert await sb.get(MSG_ID) is None
        response = ctx._responses[0]['args'][0]
        assert 'could not be deleted' in response
