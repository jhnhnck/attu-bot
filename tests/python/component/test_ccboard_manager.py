# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_ccboard_manager | settled-entry pickup query."""

import time

import pytest
import pytest_asyncio

from attu_models import MessageAuthor, MessageContent, MessageDocument, MessageRefs
from nova_core.ccboard.documents import BoardEntryDocument
from nova_core.ccboard.repositories import EntryRepository


pytestmark = pytest.mark.component

test_guild = 1234567890
other_guild = 9999999999
channel_id = 5555555555
author_id = 100000010


def _now() -> int:
    return int(time.time())


def _snapshot(message_id: int) -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=test_guild,
        channel_id=channel_id,
        author=MessageAuthor(id=author_id, name=f'user-{author_id}', bot=False),
        content=MessageContent(text='hello'),
        refs=MessageRefs(),
        created_at=_now() - 3600,
    )


def _entry(
    message_id: int,
    *,
    guild: int = test_guild,
    is_dirty: bool = True,
    last_reaction_at: int = 0,
) -> BoardEntryDocument:
    return BoardEntryDocument(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild,
        author_id=author_id,
        net_points=2,
        positive_points=2,
        last_reaction_at=last_reaction_at,
        is_dirty=is_dirty,
        snapshot=_snapshot(message_id),
    )


@pytest_asyncio.fixture
async def entry_repo(component_db):
    repo = EntryRepository(component_db)
    await repo.init_indexes()
    return repo


class TestFindSettled:
    async def test_returns_only_dirty_settled_entries(self, entry_repo):
        """only entries where is_dirty=True and last_reaction_at <= now-debounce are returned"""
        now = _now()
        # dirty + settled
        await entry_repo.upsert(_entry(1001, is_dirty=True, last_reaction_at=now - 120))
        # dirty but still within debounce window
        await entry_repo.upsert(_entry(1002, is_dirty=True, last_reaction_at=now - 30))
        # not dirty
        await entry_repo.upsert(_entry(1003, is_dirty=False, last_reaction_at=now - 120))
        # different guild
        await entry_repo.upsert(_entry(1004, guild=other_guild, is_dirty=True, last_reaction_at=now - 120))

        results = await entry_repo.find_settled(test_guild, now=now, debounce_seconds=60, limit=50)
        message_ids = {e.message_id for e in results}
        assert message_ids == {1001}

    async def test_respects_limit(self, entry_repo):
        """find_settled honors the limit parameter"""
        now = _now()
        for mid in range(2001, 2011):
            await entry_repo.upsert(_entry(mid, is_dirty=True, last_reaction_at=now - 120))

        results = await entry_repo.find_settled(test_guild, now=now, debounce_seconds=60, limit=3)
        assert len(results) == 3

    async def test_empty_when_nothing_dirty(self, entry_repo):
        """no dirty entries -> empty list"""
        now = _now()
        await entry_repo.upsert(_entry(3001, is_dirty=False, last_reaction_at=now - 120))

        results = await entry_repo.find_settled(test_guild, now=now, debounce_seconds=60, limit=50)
        assert results == []
