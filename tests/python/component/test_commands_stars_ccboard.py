# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_commands_stars_ccboard | /stars random/lost/leaderboard against ccboard.

end-to-end tests using real EntryRepository + ReactionRepository. discord gateway
objects (bot, interaction) are faked; DB queries run against a live FerretDB.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from attu_models import BoardEntryDocument, MessageAuthor, MessageContent, MessageDocument, MessageRefs
from doom_bot.config import GuildCCBoard
from doom_bot.database.repositories import EntryRepository, ReactionRepository


pytestmark = pytest.mark.component

test_guild = 1234567890
ccboard_channel = 4000000020
msg_channel = 4000000021
author_a = 100000030
author_b = 100000031
author_c = 100000032
reactor_a = 200000030
reactor_b = 200000031

msg_id_a = 7771000001
msg_id_b = 7771000002
msg_id_c = 7771000003
board_post_a = 8881000001


def _snapshot(msg_id: int, author_id: int = author_a) -> MessageDocument:
    return MessageDocument(
        message_id=msg_id,
        guild_id=test_guild,
        channel_id=msg_channel,
        author=MessageAuthor(id=author_id, name='TestUser', bot=False),
        content=MessageContent(text=f'message {msg_id}'),
        refs=MessageRefs(),
        created_at=1704067200,
    )


def _entry(msg_id: int, author_id: int = author_a, *, positive_points: int = 3, net_points: int = 3, starboard_message_id: int | None = board_post_a) -> BoardEntryDocument:
    return BoardEntryDocument(
        message_id=msg_id,
        channel_id=msg_channel,
        guild_id=test_guild,
        author_id=author_id,
        positive_points=positive_points,
        net_points=net_points,
        starboard_message_id=starboard_message_id,
        snapshot=_snapshot(msg_id, author_id),
    )


@pytest_asyncio.fixture
async def cc_repos(component_db, make_guild):
    """wire real ccboard repos into module singletons; guild has ccboard.enabled=True."""
    reaction_repo = ReactionRepository(component_db)
    entry_repo = EntryRepository(component_db)
    await reaction_repo.init_indexes()
    await entry_repo.init_indexes()

    cfg = make_guild(guild_id=test_guild)
    cfg.ccboard = GuildCCBoard(
        enabled=True,
        channel_id=ccboard_channel,
        emojis={'⭐': 1},
        super_bonus=0,
        threshold=2,
        points_label='stars',
    )

    import doom_bot.ccboard as _ccboard

    _ccboard._reaction_repo = reaction_repo
    _ccboard._entry_repo = entry_repo

    yield {'entry': entry_repo, 'reaction': reaction_repo, 'cfg': cfg}

    _ccboard._reaction_repo = None
    _ccboard._entry_repo = None


class TestCCBoardStarsRandom:
    async def test_random_returns_entry_with_board_post(self, cc_repos, mock_ctx_factory):
        """ccboard random: seeded entry with starboard_message_id appears in response."""
        await cc_repos['entry'].upsert(_entry(msg_id_a, positive_points=3, starboard_message_id=board_post_a))

        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_random

        await stars_random(ctx)

        assert len(ctx._responses) == 1
        content = ctx._responses[0]['kwargs'].get('content', '')
        assert str(msg_id_a) in content
        assert 'stars' in content

    async def test_random_no_match_responds_ephemeral(self, cc_repos, mock_ctx_factory):
        """ccboard random: empty db → 'no messages found' ephemeral."""
        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_random

        await stars_random(ctx)

        assert len(ctx._responses) == 1
        assert 'no messages found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_random_only_returns_entries_with_board_post(self, cc_repos, mock_ctx_factory):
        """ccboard random: entry without starboard_message_id is excluded."""
        # entry below threshold, no board post — should not be returned by random
        await cc_repos['entry'].upsert(_entry(msg_id_a, positive_points=1, starboard_message_id=None))

        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_random

        await stars_random(ctx)

        assert 'no messages found' in ctx._responses[0]['args'][0]

    async def test_random_appends_display_message_id(self, cc_repos, mock_ctx_factory):
        """ccboard random: response message id is appended to entry.display_message_ids."""
        await cc_repos['entry'].upsert(_entry(msg_id_a, positive_points=3, starboard_message_id=board_post_a))

        response_msg_id = 9999000001
        ctx = mock_ctx_factory(guild_id=test_guild)
        ctx.interaction.original_response = AsyncMock(return_value=type('M', (), {'id': response_msg_id})())

        from doom_bot.commands.stars import stars_random

        await stars_random(ctx)

        updated = await cc_repos['entry'].get(msg_id_a)
        assert response_msg_id in updated.display_message_ids

    async def test_lost_returns_below_threshold_entry(self, cc_repos, mock_ctx_factory):
        """ccboard lost: entry with positive_points=1 and no board post is returned."""
        await cc_repos['entry'].upsert(_entry(msg_id_b, positive_points=1, starboard_message_id=None))
        # also seed a random-eligible entry to confirm it's excluded
        await cc_repos['entry'].upsert(_entry(msg_id_a, positive_points=3, starboard_message_id=board_post_a))

        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_lost

        await stars_lost(ctx)

        assert len(ctx._responses) == 1
        content = ctx._responses[0]['kwargs'].get('content', '')
        assert str(msg_id_b) in content
        assert str(msg_id_a) not in content

    async def test_lost_no_match_responds_ephemeral(self, cc_repos, mock_ctx_factory):
        """ccboard lost: no entries with positive_points=1 → 'no messages found'."""
        ctx = mock_ctx_factory(guild_id=test_guild)

        from doom_bot.commands.stars import stars_lost

        await stars_lost(ctx)

        assert 'no messages found' in ctx._responses[0]['args'][0]
        assert ctx._responses[0]['kwargs'].get('ephemeral') is True

    async def test_legacy_path_taken_when_ccboard_disabled(self, cc_repos, mock_ctx_factory):
        """when ccboard.enabled=False the legacy sb_repo path is used."""
        cc_repos['cfg'].ccboard.enabled = False

        ctx = mock_ctx_factory(guild_id=test_guild)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_random = AsyncMock(return_value=None)

        with patch('doom_bot.commands.stars._get_sb_repo', return_value=mock_sb_repo):
            from doom_bot.commands.stars import stars_random

            await stars_random(ctx)

        mock_sb_repo.get_random.assert_called_once()
