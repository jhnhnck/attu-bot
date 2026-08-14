# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_commands_fix_stars_convert | starboard → ccboard migration."""

import time

import pytest
import pytest_asyncio

from nova_core.ccboard.repositories import EntryRepository, ReactionRepository
from nova_core.config import GuildCCBoard
from nova_core.database.models import (
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    StarredMessageDocument,
)
from nova_core.database.repositories import (
    MessageRepository,
    StarboardRepository,
)


pytestmark = pytest.mark.component

test_guild = 1234567890
sb_channel = 4000000010
msg_channel = 4000000011
author_a = 100000010
author_bot = 100000099
user_1 = 200000010
user_2 = 200000020
user_3 = 200000030
reply_target_user = 200000040

msg_id = 8881000001
msg_id_bot_reply = 8881000002
reply_target_msg_id = 8881000099
sb_post_id = 8882000001


def _now() -> int:
    return int(time.time())


def _starred(message_id: int, *, author_id: int = author_a, reactions: dict | None = None, super_reactions: dict | None = None, starboard_message_id: int | None = sb_post_id) -> StarredMessageDocument:
    return StarredMessageDocument(
        message_id=message_id,
        channel_id=msg_channel,
        guild_id=test_guild,
        author_id=author_id,
        reactions=reactions if reactions is not None else {'⭐': [user_1]},
        super_reactions=super_reactions if super_reactions is not None else {},
        total_reactions=sum(len(v) for v in (reactions or {'⭐': [user_1]}).values()),
        starboard_message_id=starboard_message_id,
    )


def _message(message_id: int, *, author_id: int = author_a, bot: bool = False, reply_to: int | None = None) -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=test_guild,
        channel_id=msg_channel,
        author=MessageAuthor(id=author_id, name=f'user-{author_id}', bot=bot),
        content=MessageContent(text='hello world'),
        refs=MessageRefs(reply_to=reply_to),
        created_at=_now() - 3600,
    )


@pytest_asyncio.fixture
async def convert_repos(component_db, make_guild):
    """wire real repositories into module singletons and configure ccboard emoji weights"""
    sb_repo = StarboardRepository(component_db)
    msg_repo = MessageRepository(component_db)
    reaction_repo = ReactionRepository(component_db)
    entry_repo = EntryRepository(component_db)

    await sb_repo.init_indexes()
    await msg_repo.init_indexes()
    await reaction_repo.init_indexes()
    await entry_repo.init_indexes()

    cfg = make_guild(guild_id=test_guild)
    cfg.starboard.channel_id = sb_channel
    cfg.starboard.emojis = {'⭐': '#EEDD20'}
    cfg.ccboard = GuildCCBoard(
        enabled=True,
        channel_id=sb_channel,
        emojis={'⭐': 1, '💀': -1},
        super_bonus=2,
        threshold=2,
    )

    import nova_core.ccboard as _ccboard
    import nova_core.client.messages as _messages
    import nova_core.starboard.handlers as _starboard

    _starboard._starboard_repo = sb_repo
    _messages._message_repo = msg_repo
    _ccboard._reaction_repo = reaction_repo
    _ccboard._entry_repo = entry_repo

    yield {'sb': sb_repo, 'msg': msg_repo, 'reaction': reaction_repo, 'entry': entry_repo, 'cfg': cfg}

    _starboard._starboard_repo = None
    _messages._message_repo = None
    _ccboard._reaction_repo = None
    _ccboard._entry_repo = None


class TestConvertMigration:
    async def test_creates_entry_and_reactions(self, convert_repos):
        """one starred message with three regular star reactions migrates to one entry and three reaction docs"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1, user_2, user_3]}))
        await convert_repos['msg'].upsert(_message(msg_id))

        stats = await job_convert_starboard_to_ccboard(test_guild)

        assert stats['entries_processed'] == 1
        assert stats['reactions_migrated'] == 3
        assert stats['placeholder'] == 0

        entry = await convert_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.author_id == author_a
        assert entry.starboard_message_id == sb_post_id
        assert entry.snapshot.message_id == msg_id
        assert entry.net_points == 3
        assert entry.positive_points == 3
        assert entry.is_dirty is False

        reactions = await convert_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert len(reactions) == 3
        assert {r.user_id for r in reactions} == {user_1, user_2, user_3}
        assert all(r.point_value == 1 for r in reactions)
        assert all(r.is_super is False for r in reactions)
        assert all(r.source_message_id == msg_id for r in reactions)

    async def test_super_reaction_carries_bonus_and_overrides_regular(self, convert_repos):
        """user in both reactions and super_reactions for same emoji gets the super (higher-value) record"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        starred = _starred(
            msg_id,
            reactions={'⭐': [user_1, user_2]},
            super_reactions={'⭐': [user_1]},
        )
        starred.total_reactions = 2  # legacy raw count of distinct user-reactions
        await convert_repos['sb'].upsert(starred)
        await convert_repos['msg'].upsert(_message(msg_id))

        await job_convert_starboard_to_ccboard(test_guild)

        reactions = {r.user_id: r for r in await convert_repos['reaction'].list_for_message(msg_id, include_removed=False)}
        assert len(reactions) == 2
        assert reactions[user_1].is_super is True
        assert reactions[user_1].point_value == 1 + 2  # weight + super_bonus
        assert reactions[user_2].is_super is False
        assert reactions[user_2].point_value == 1

        entry = await convert_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.net_points == 1 + (1 + 2)
        assert entry.positive_points == 1 + (1 + 2)

    async def test_negative_emoji_reduces_net_but_not_positive(self, convert_repos):
        """💀 has weight -1; net drops, positive stays at the ⭐ count"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1, user_2], '💀': [user_3]}))
        await convert_repos['msg'].upsert(_message(msg_id))

        await job_convert_starboard_to_ccboard(test_guild)

        entry = await convert_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.net_points == 1 + 1 - 1
        assert entry.positive_points == 1 + 1

    async def test_bot_reply_attribution_credits_user(self, convert_repos):
        """starred message authored by a bot that replies to a user is credited to that user via effective_author_id"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['msg'].upsert(_message(reply_target_msg_id, author_id=reply_target_user))
        await convert_repos['msg'].upsert(_message(msg_id_bot_reply, author_id=author_bot, bot=True, reply_to=reply_target_msg_id))
        await convert_repos['sb'].upsert(_starred(msg_id_bot_reply, author_id=author_bot, reactions={'⭐': [user_1]}))

        await job_convert_starboard_to_ccboard(test_guild)

        entry = await convert_repos['entry'].get(msg_id_bot_reply)
        assert entry is not None
        assert entry.author_id == author_bot
        assert entry.effective_author_id == reply_target_user
        assert entry.reply_snapshot is not None
        assert entry.reply_snapshot.author.id == reply_target_user

    async def test_missing_message_uses_placeholder(self, convert_repos):
        """no MessageDocument and no discord fallback (channel not in cache) → placeholder snapshot"""
        from unittest.mock import MagicMock, patch

        import discord

        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1]}))
        # no message inserted; bot.get_channel returns None and fetch_channel raises NotFound

        with patch('nova_core.ccboard.migration.bot.get_channel', return_value=None), patch('nova_core.ccboard.migration.bot.fetch_channel', side_effect=discord.NotFound(MagicMock(), 'not found')):
            stats = await job_convert_starboard_to_ccboard(test_guild)

        assert stats['placeholder'] == 1
        entry = await convert_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.snapshot.created_at == 0
        assert entry.snapshot.author.id == author_a

    async def test_idempotent(self, convert_repos):
        """running the migration twice yields the same final state"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1, user_2]}))
        await convert_repos['msg'].upsert(_message(msg_id))

        stats_1 = await job_convert_starboard_to_ccboard(test_guild)
        entry_1 = await convert_repos['entry'].get(msg_id)
        reactions_1 = await convert_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert entry_1 is not None

        stats_2 = await job_convert_starboard_to_ccboard(test_guild)
        entry_2 = await convert_repos['entry'].get(msg_id)
        reactions_2 = await convert_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert entry_2 is not None

        assert stats_2['entries_processed'] == stats_1['entries_processed']
        assert stats_2['reactions_migrated'] == stats_1['reactions_migrated']
        assert entry_2.net_points == entry_1.net_points
        assert entry_2.positive_points == entry_1.positive_points
        assert entry_2.starboard_message_id == entry_1.starboard_message_id
        # the second run should not overwrite last_synced_at with a fresh value -
        # existing entries preserve it so the manager doesn't re-pick them
        assert entry_2.last_synced_at == entry_1.last_synced_at
        assert {r.user_id for r in reactions_2} == {r.user_id for r in reactions_1}

    async def test_skips_unweighted_emojis(self, convert_repos):
        """reactions on emojis not in ccboard.emojis are skipped (counted in stats), not weighted as 0"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1], '🦄': [user_2, user_3]}))
        await convert_repos['msg'].upsert(_message(msg_id))

        stats = await job_convert_starboard_to_ccboard(test_guild)

        assert stats['reactions_migrated'] == 1
        assert stats['skipped_unweighted_emojis'] == 2

        reactions = await convert_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert len(reactions) == 1
        assert reactions[0].user_id == user_1

    async def test_no_emojis_configured_short_circuits(self, convert_repos):
        """guild with empty ccboard.emojis returns early without writing anything"""
        from nova_core.ccboard.migration import job_convert_starboard_to_ccboard

        convert_repos['cfg'].ccboard.emojis = {}
        await convert_repos['sb'].upsert(_starred(msg_id, reactions={'⭐': [user_1]}))
        await convert_repos['msg'].upsert(_message(msg_id))

        stats = await job_convert_starboard_to_ccboard(test_guild)

        assert stats['skipped_no_config'] == 1
        assert stats['entries_processed'] == 0
        assert await convert_repos['entry'].get(msg_id) is None
