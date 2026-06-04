# SPDX-License-Identifier: Apache-2.0
"""tests.python.component.test_commands_fix_ccboard_recount | /fix ccboard recount end-to-end."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from attu_models import (
    BoardEntryDocument,
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    ReactionDocument,
)
from doom_bot.config import GuildCCBoard
from doom_bot.database.repositories import EntryRepository, ReactionRepository


pytestmark = pytest.mark.component

test_guild = 1234567890
ccboard_channel_id = 4000000010
msg_channel = 4000000011
author_a = 100000010
reactor_a = 200000010
reactor_b = 200000020
bot_user_id = 100000099
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


def _reaction(user_id: int, emoji: str = emoji_star, *, point_value: int = 1) -> ReactionDocument:
    return ReactionDocument(
        message_id=msg_id,
        user_id=user_id,
        guild_id=test_guild,
        author_id=author_a,
        emoji_str=emoji,
        is_super=False,
        point_value=point_value,
        reacted_at=1704067200,
        source_message_id=msg_id,
        source_channel_id=msg_channel,
    )


def _user_mock(user_id: int, *, bot: bool = False) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.bot = bot
    return u


def _discord_msg_with(reactions: list[tuple[str, list, bool]]) -> MagicMock:
    """build a fake discord.Message exposing only the attributes the auditor reads"""

    msg = MagicMock()
    msg.id = msg_id
    msg_reactions = []
    for emoji_str, users, is_burst in reactions:
        r = MagicMock()
        r.emoji = emoji_str
        r.is_burst = is_burst

        async def _users_iter(_users=users):
            for u in _users:
                yield u

        r.users = MagicMock(side_effect=lambda _users=users: _users_iter(_users))
        msg_reactions.append(r)
    msg.reactions = msg_reactions
    return msg


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

    import doom_bot.ccboard as _ccboard

    _ccboard._reaction_repo = reaction_repo
    _ccboard._entry_repo = entry_repo

    yield {'reaction': reaction_repo, 'entry': entry_repo, 'cfg': cfg}

    _ccboard._reaction_repo = None
    _ccboard._entry_repo = None


class TestFixCCBoardRecount:
    async def test_invalid_link_responds_with_failure(self, fix_cc_repos, mock_ctx_factory):
        """malformed message link short-circuits before touching any repo"""
        from doom_bot.commands.fix import fix_ccboard_recount

        ctx = mock_ctx_factory(guild_id=test_guild)
        await fix_ccboard_recount(ctx, message_link='not-a-link', confirm=False)

        assert any('invalid message link' in r['args'][0] for r in ctx._responses)

    async def test_link_from_other_guild_rejected(self, fix_cc_repos, mock_ctx_factory):
        """recount refuses links targeting a different guild"""
        from doom_bot.commands.fix import fix_ccboard_recount

        ctx = mock_ctx_factory(guild_id=test_guild)
        other_link = f'https://discord.com/channels/{test_guild + 1}/{msg_channel}/{msg_id}'
        await fix_ccboard_recount(ctx, message_link=other_link, confirm=False)

        assert any('different server' in r['args'][0] for r in ctx._responses)

    async def test_dry_run_reports_diff_without_mutating(self, fix_cc_repos, mock_ctx_factory, monkeypatch):
        """live discord shows reactor_a/star, db is empty: dry-run reports add=1 and writes nothing"""
        from doom_bot.ccboard import auditor as auditor_mod
        from doom_bot.commands.fix import fix_ccboard_recount

        await fix_cc_repos['entry'].upsert(_entry())

        async def _fake_fetch(*_a, **_kw):
            return _discord_msg_with([(emoji_star, [_user_mock(reactor_a)], False)])

        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake_fetch)

        ctx = mock_ctx_factory(guild_id=test_guild)
        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/{msg_id}'

        await fix_ccboard_recount(ctx, message_link=link, confirm=False)

        # respond was called ephemerally with a dry-run summary
        assert ctx.defer.await_count == 1
        assert any('dry_run' in r['args'][0] for r in ctx._responses)
        assert any('add=1' in r['args'][0] for r in ctx._responses)

        # repo should be untouched
        assert await fix_cc_repos['reaction'].list_for_message(msg_id, include_removed=True) == []

    async def test_apply_path_writes_reaction_and_marks_dirty(self, fix_cc_repos, mock_ctx_factory, monkeypatch):
        """confirm=True applies the diff: reactor_a gets a ReactionDocument, entry net_points reflects it"""
        from doom_bot.ccboard import auditor as auditor_mod
        from doom_bot.ccboard import watcher as watcher_mod
        from doom_bot.commands.fix import fix_ccboard_recount

        await fix_cc_repos['entry'].upsert(_entry())

        async def _fake_fetch(*_a, **_kw):
            return _discord_msg_with([(emoji_star, [_user_mock(reactor_a)], False)])

        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake_fetch)
        monkeypatch.setattr(watcher_mod, '_safe_remove_reaction', AsyncMock(return_value=True))

        ctx = mock_ctx_factory(guild_id=test_guild)
        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/{msg_id}'

        await fix_ccboard_recount(ctx, message_link=link, confirm=True)

        assert any('APPLIED' in r['args'][0] for r in ctx._responses)

        live_reactions = await fix_cc_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert len(live_reactions) == 1
        assert live_reactions[0].user_id == reactor_a
        assert live_reactions[0].point_value == 1

        entry = await fix_cc_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.net_points == 1
        assert entry.positive_points == 1
        assert entry.is_dirty is True

    async def test_apply_path_recounts_stale_record_with_fresh_point_value(self, fix_cc_repos, mock_ctx_factory, monkeypatch):
        """phase 2.3: a record predating cfg.weights_updated_at is re-snapshotted with current cfg point_value and stamped"""
        from doom_bot.ccboard import auditor as auditor_mod
        from doom_bot.ccboard import watcher as watcher_mod
        from doom_bot.commands.fix import fix_ccboard_recount

        # seed: existing reaction snapshotted with the old weight, weights_updated_at later than the seed's reacted_at
        await fix_cc_repos['entry'].upsert(_entry())
        await fix_cc_repos['reaction'].upsert_active(_reaction(reactor_a, point_value=1))
        # bump star weight in cfg AFTER the reaction was recorded; mirrors a web save handler bump
        fix_cc_repos['cfg'].ccboard.emojis[emoji_star] = 7
        fix_cc_repos['cfg'].ccboard.weights_updated_at = 9_999_999_999

        async def _fake_fetch(*_a, **_kw):
            return _discord_msg_with([(emoji_star, [_user_mock(reactor_a)], False)])

        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake_fetch)
        monkeypatch.setattr(watcher_mod, '_safe_remove_reaction', AsyncMock(return_value=True))

        ctx = mock_ctx_factory(guild_id=test_guild)
        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/{msg_id}'

        await fix_ccboard_recount(ctx, message_link=link, confirm=True)

        # exactly one active reaction; point_value reflects the new weight; last_recounted_at stamped
        live_reactions = await fix_cc_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert len(live_reactions) == 1
        assert live_reactions[0].point_value == 7
        assert live_reactions[0].last_recounted_at is not None

        # entry net_points reflects the recounted weight
        entry = await fix_cc_repos['entry'].get(msg_id)
        assert entry is not None
        assert entry.net_points == 7
        assert any('recount=1' in r['args'][0] for r in ctx._responses)

    async def test_guild_wide_reconcile_reports_per_entry_results(self, fix_cc_repos, mock_ctx_factory, monkeypatch):
        """no message_link path: calls reconcile_guild, response includes processed count"""
        from doom_bot.ccboard import auditor as auditor_mod
        from doom_bot.ccboard import watcher as watcher_mod
        from doom_bot.commands.fix import fix_ccboard_recount

        await fix_cc_repos['entry'].upsert(_entry())

        async def _fake_fetch(*_a, **_kw):
            return _discord_msg_with([(emoji_star, [_user_mock(reactor_a)], False)])

        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake_fetch)
        monkeypatch.setattr(watcher_mod, '_safe_remove_reaction', AsyncMock(return_value=True))

        ctx = mock_ctx_factory(guild_id=test_guild)
        await fix_ccboard_recount(ctx, message_link=None, confirm=False)

        # the no-link path now calls reconcile_guild; response contains processed count
        assert any('processed=1/1' in r['args'][0] for r in ctx._responses)

    async def test_distinct_channel_ids_returns_seeded_channels(self, fix_cc_repos):
        """distinct_channel_ids returns the set of channel_ids from seeded entries (no duplicates)."""
        entry_repo = fix_cc_repos['entry']
        ch1, ch2 = 7770000001, 7770000002
        # two entries in ch1, one in ch2, plus the default _entry() already in ch msg_channel
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

    async def test_apply_path_strips_self_and_bot_via_safe_remove(self, fix_cc_repos, mock_ctx_factory, monkeypatch):
        """author and bot reactors trigger _safe_remove_reaction during apply, never get added to the db"""
        from doom_bot.ccboard import auditor as auditor_mod
        from doom_bot.ccboard import watcher as watcher_mod
        from doom_bot.commands.fix import fix_ccboard_recount

        await fix_cc_repos['entry'].upsert(_entry())

        async def _fake_fetch(*_a, **_kw):
            return _discord_msg_with([
                (
                    emoji_star,
                    [
                        _user_mock(author_a),  # self-star
                        _user_mock(bot_user_id, bot=True),  # bot reactor
                        _user_mock(reactor_a),  # legit
                    ],
                    False,
                )
            ])

        safe_remove = AsyncMock(return_value=True)
        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake_fetch)
        monkeypatch.setattr(watcher_mod, '_safe_remove_reaction', safe_remove)

        ctx = mock_ctx_factory(guild_id=test_guild)
        link = f'https://discord.com/channels/{test_guild}/{msg_channel}/{msg_id}'

        await fix_ccboard_recount(ctx, message_link=link, confirm=True)

        live_reactions = await fix_cc_repos['reaction'].list_for_message(msg_id, include_removed=False)
        assert {r.user_id for r in live_reactions} == {reactor_a}
        # _safe_remove_reaction called for both stripped users
        assert safe_remove.await_count == 2
