# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_ccboard_entry_repository | EntryRepository behavior against real MongoDB."""

import pytest
import pytest_asyncio

from attu_models import MessageAuthor, MessageContent, MessageDocument, MessageRefs
from nova_core.ccboard.documents import BoardEntryDocument
from nova_core.ccboard.repositories import EntryRepository, ReactionRepository
from nova_core.config import GuildCCBoard


pytestmark = pytest.mark.component

test_guild = 1234567890
ccboard_channel_id = 4000000010
msg_channel = 4000000011
author_a = 100000010
msg_id = 8881000001

emoji_star = '⭐'
emoji_fire = '🔥'


def _snapshot() -> MessageDocument:
    return MessageDocument(
        message_id=msg_id,
        guild_id=test_guild,
        channel_id=msg_channel,
        author=MessageAuthor(id=author_a, name='AuthorUser', bot=False),
        content=MessageContent(text='hello world'),
        refs=MessageRefs(),
        created_at=1704067200,
    )


def _entry() -> BoardEntryDocument:
    return BoardEntryDocument(
        message_id=msg_id,
        channel_id=msg_channel,
        guild_id=test_guild,
        author_id=author_a,
        snapshot=_snapshot(),
    )


@pytest_asyncio.fixture
async def fix_cc_repos(component_db, make_guild):
    """wire real ccboard repos into module singletons and configure the guild."""
    reaction_repo = ReactionRepository(component_db)
    entry_repo = EntryRepository(component_db)
    await reaction_repo.init_indexes()
    await entry_repo.init_indexes()

    cfg = make_guild(guild_id=test_guild)
    cfg.ccboard = GuildCCBoard(
        enabled=True,
        channel_id=ccboard_channel_id,
        emojis={emoji_star: 1, emoji_fire: 2},
        super_bonus=1,
        threshold=2,
    )

    import nova_core.ccboard as _ccboard

    _ccboard._reaction_repo = reaction_repo
    _ccboard._entry_repo = entry_repo

    yield {'reaction': reaction_repo, 'entry': entry_repo, 'cfg': cfg}

    _ccboard._reaction_repo = None
    _ccboard._entry_repo = None


class TestEntryRepositoryDistinctChannelIds:
    async def test_distinct_channel_ids_returns_seeded_channels(self, fix_cc_repos):
        """distinct_channel_ids returns the set of channel_ids from seeded entries (no duplicates)."""
        entry_repo = fix_cc_repos['entry']
        ch1, ch2 = 7770000001, 7770000002
        # seed base entry in msg_channel, then two more entries across ch1/ch2
        await entry_repo.upsert(_entry())
        e1 = _entry()
        e1.message_id = msg_id + 1
        e1.channel_id = ch1
        e2 = _entry()
        e2.message_id = msg_id + 2
        e2.channel_id = ch1
        e3 = _entry()
        e3.message_id = msg_id + 3
        e3.channel_id = ch2
        for e in [e1, e2, e3]:
            await entry_repo.upsert(e)

        channels = await entry_repo.distinct_channel_ids(test_guild)
        assert set(channels) == {msg_channel, ch1, ch2}
        assert len(channels) == len(set(channels))  # no duplicates
