# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_auditor | unit tests for the ccboard auditor task."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from attu_models import MessageAuthor, MessageContent, MessageDocument, MessageRefs
from nova_core import ccboard
from nova_core.ccboard import auditor as auditor_mod
from nova_core.ccboard import watcher as watcher_mod
from nova_core.ccboard.auditor import (
    AuditorTask,
    PassResult,
    _compute_diff,
    _is_stale,
    _LiveReaction,
    auditor_task,
)
from nova_core.ccboard.documents import BoardEntryDocument, ReactionDocument
from nova_core.config import GuildCCBoard
from tests.conftest import test_guild


# --- Constants ---

guild_id = test_guild
channel_id = 5555555555
ccboard_channel_id = 9999999999
message_id = 111000111000111000
author_id = 573360359566737409
reactor_a = 100000001
reactor_b = 100000002
bot_user_id = 100000099

emoji_star = '⭐'
emoji_fire = '🔥'
emoji_skull = '💀'


# --- Fixtures ---


@pytest.fixture
def cfg():
    return GuildCCBoard(
        enabled=True,
        channel_id=ccboard_channel_id,
        emojis={emoji_star: 1, emoji_fire: 2, emoji_skull: -1},
        super_bonus=1,
        threshold=2,
        points_label='stars',
    )


@pytest.fixture
def make_guild_ccboard(make_guild, cfg):
    gc = make_guild()
    gc.ccboard = cfg
    return gc


@pytest.fixture
def snapshot():
    return MessageDocument(
        message_id=message_id,
        guild_id=test_guild,
        channel_id=channel_id,
        author=MessageAuthor(id=author_id, name='AuthorUser', bot=False),
        content=MessageContent(text='hello world'),
        refs=MessageRefs(),
        created_at=1704067200,
    )


@pytest.fixture
def entry_doc(snapshot):
    return BoardEntryDocument(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=test_guild,
        author_id=author_id,
        snapshot=snapshot,
    )


@pytest.fixture
def reaction_repo():
    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=None)
    repo.upsert_active = AsyncMock(return_value=None)
    repo.soft_delete = AsyncMock(return_value=None)
    repo.soft_delete_all_for_message = AsyncMock(return_value=0)
    repo.soft_delete_emoji = AsyncMock(return_value=0)
    repo.list_for_message = AsyncMock(return_value=[])
    repo.aggregate_points = AsyncMock(return_value=(3, 3))
    return repo


@pytest.fixture
def entry_repo(entry_doc):
    repo = MagicMock()
    repo.get = AsyncMock(return_value=entry_doc)
    repo.set_points = AsyncMock(return_value=None)
    repo.mark_dirty = AsyncMock(return_value=None)
    return repo


@pytest.fixture(autouse=True)
def _wire_repos(reaction_repo, entry_repo, monkeypatch):
    monkeypatch.setattr(ccboard, '_reaction_repo', reaction_repo)
    monkeypatch.setattr(ccboard, '_entry_repo', entry_repo)
    yield
    ccboard._pending_bot_removals.clear()
    ccboard._locks.clear()


@pytest.fixture
def stub_safe_remove(monkeypatch):
    """patch the watcher's _safe_remove_reaction so reconcile's apply path doesn't touch discord"""
    stub = AsyncMock(return_value=True)
    monkeypatch.setattr(watcher_mod, '_safe_remove_reaction', stub)
    return stub


def _live(user_id: int, emoji: str, *, is_super: bool = False, is_bot_reactor: bool = False) -> _LiveReaction:
    return _LiveReaction(user_id=user_id, emoji_str=emoji, is_super=is_super, is_bot_reactor=is_bot_reactor)


def _db_reaction(
    user_id: int,
    emoji: str,
    *,
    is_super: bool = False,
    point_value: int = 1,
    reacted_at: int = 1704067200,
    last_recounted_at: int | None = None,
) -> ReactionDocument:
    return ReactionDocument(
        message_id=message_id,
        user_id=user_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji,
        is_super=is_super,
        point_value=point_value,
        reacted_at=reacted_at,
        source_message_id=message_id,
        source_channel_id=channel_id,
        last_recounted_at=last_recounted_at,
    )


# --- _compute_diff tests ---


class TestComputeDiff:
    def test_add_only(self):
        """user reacted live, nothing in db: counts as an add"""
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star)],
            db_active={},
            credited_author_id=author_id,
            partial=False,
        )
        assert len(diff.to_add) == 1
        assert diff.to_add[0].user_id == reactor_a
        assert diff.to_replace == []
        assert diff.to_remove == []
        assert diff.matching_count == 0

    def test_remove_only_when_not_partial(self):
        """db has user, live is empty, partial=False: counts as a remove"""
        diff = _compute_diff(
            live_rows=[],
            db_active={reactor_a: _db_reaction(reactor_a, emoji_star)},
            credited_author_id=author_id,
            partial=False,
        )
        assert diff.to_add == []
        assert len(diff.to_remove) == 1
        assert diff.to_remove[0].user_id == reactor_a

    def test_partial_suppresses_remove(self):
        """db has user but live empty under partial=True: must not remove (could be pagination loss)"""
        diff = _compute_diff(
            live_rows=[],
            db_active={reactor_a: _db_reaction(reactor_a, emoji_star)},
            credited_author_id=author_id,
            partial=True,
        )
        assert diff.to_remove == []
        assert diff.to_add == []
        assert diff.matching_count == 0

    def test_replace_when_emoji_changes(self):
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_fire)],
            db_active={reactor_a: _db_reaction(reactor_a, emoji_star)},
            credited_author_id=author_id,
            partial=False,
        )
        assert diff.to_add == []
        assert diff.to_remove == []
        assert len(diff.to_replace) == 1
        live, db_row = diff.to_replace[0]
        assert live.emoji_str == emoji_fire
        assert db_row.emoji_str == emoji_star

    def test_replace_when_super_flag_flips(self):
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star, is_super=True)],
            db_active={reactor_a: _db_reaction(reactor_a, emoji_star, is_super=False)},
            credited_author_id=author_id,
            partial=False,
        )
        assert len(diff.to_replace) == 1
        assert diff.matching_count == 0

    def test_matching(self):
        """same user, same emoji, same super flag: counted as matching, not added or replaced"""
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star)],
            db_active={reactor_a: _db_reaction(reactor_a, emoji_star)},
            credited_author_id=author_id,
            partial=False,
        )
        assert diff.to_add == []
        assert diff.to_replace == []
        assert diff.to_remove == []
        assert diff.matching_count == 1

    def test_strip_self_reaction(self):
        """author reacting to their own message gets stripped, not added or replaced"""
        diff = _compute_diff(
            live_rows=[_live(author_id, emoji_star)],
            db_active={},
            credited_author_id=author_id,
            partial=False,
        )
        assert diff.to_add == []
        assert len(diff.to_strip_from_discord) == 1
        assert diff.to_strip_from_discord[0].user_id == author_id

    def test_strip_bot_reaction(self):
        """bot reactors get stripped from discord, never added"""
        diff = _compute_diff(
            live_rows=[_live(bot_user_id, emoji_star, is_bot_reactor=True)],
            db_active={},
            credited_author_id=author_id,
            partial=False,
        )
        assert diff.to_add == []
        assert len(diff.to_strip_from_discord) == 1
        assert diff.to_strip_from_discord[0].is_bot_reactor is True

    def test_strip_extras_one_vote(self):
        """same user with two emojis: first is added, second goes to strip_extras"""
        diff = _compute_diff(
            live_rows=[
                _live(reactor_a, emoji_star),
                _live(reactor_a, emoji_fire),
            ],
            db_active={},
            credited_author_id=author_id,
            partial=False,
        )
        assert len(diff.to_add) == 1
        assert diff.to_add[0].emoji_str == emoji_star
        assert len(diff.to_strip_extras) == 1
        assert diff.to_strip_extras[0].emoji_str == emoji_fire

    def test_recount_when_match_is_stale(self):
        """matching record whose effective freshness predates weights_updated_at moves to to_recount"""
        stale = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None)
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star)],
            db_active={reactor_a: stale},
            credited_author_id=author_id,
            partial=False,
            weights_updated_at=200,
        )
        assert diff.matching_count == 0
        assert len(diff.to_recount) == 1
        assert diff.to_recount[0] is stale

    def test_recount_skipped_when_last_recounted_after_bump(self):
        """last_recounted_at >= weights_updated_at keeps the record in matching_count"""
        fresh = _db_reaction(reactor_a, emoji_star, reacted_at=50, last_recounted_at=300)
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star)],
            db_active={reactor_a: fresh},
            credited_author_id=author_id,
            partial=False,
            weights_updated_at=200,
        )
        assert diff.matching_count == 1
        assert diff.to_recount == []

    def test_recount_zero_weights_updated_at_short_circuits(self):
        """weights_updated_at == 0 keeps every match counted; no recount work done"""
        old = _db_reaction(reactor_a, emoji_star, reacted_at=10, last_recounted_at=None)
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_star)],
            db_active={reactor_a: old},
            credited_author_id=author_id,
            partial=False,
            weights_updated_at=0,
        )
        assert diff.matching_count == 1
        assert diff.to_recount == []

    def test_recount_does_not_fire_for_replace(self):
        """a record being replaced (different emoji) skips the recount path; replace already snapshots fresh point_value"""
        stale = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None)
        diff = _compute_diff(
            live_rows=[_live(reactor_a, emoji_fire)],
            db_active={reactor_a: stale},
            credited_author_id=author_id,
            partial=False,
            weights_updated_at=200,
        )
        assert len(diff.to_replace) == 1
        assert diff.to_recount == []


class TestIsStale:
    def test_zero_updated_at_means_never_stale(self):
        rec = _db_reaction(reactor_a, emoji_star, reacted_at=10, last_recounted_at=None)
        assert _is_stale(rec, weights_updated_at=0) is False

    def test_negative_updated_at_treated_as_zero(self):
        rec = _db_reaction(reactor_a, emoji_star, reacted_at=10, last_recounted_at=None)
        assert _is_stale(rec, weights_updated_at=-5) is False

    def test_falls_back_to_reacted_at_when_no_recount(self):
        rec = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None)
        assert _is_stale(rec, weights_updated_at=200) is True
        assert _is_stale(rec, weights_updated_at=99) is False

    def test_uses_last_recounted_at_when_set(self):
        """last_recounted_at overrides reacted_at — newer recount means fresh even if reacted_at is old"""
        rec = _db_reaction(reactor_a, emoji_star, reacted_at=10, last_recounted_at=300)
        assert _is_stale(rec, weights_updated_at=200) is False

    def test_equal_timestamp_is_fresh(self):
        """strict less-than: a record stamped at exactly weights_updated_at is considered fresh"""
        rec = _db_reaction(reactor_a, emoji_star, reacted_at=10, last_recounted_at=200)
        assert _is_stale(rec, weights_updated_at=200) is False


# --- reconcile_entry tests ---


@pytest.fixture
def task():
    return AuditorTask()


@pytest.fixture
def fake_discord_msg():
    """build a mock discord.Message with a configurable .reactions list.

    .users() returns an async iterator (the watcher path uses `async for`).
    """

    def _make(reactions: list[tuple[str, list, bool]]):
        msg = MagicMock()
        msg.id = message_id

        async def _empty_iter():
            return
            yield  # pragma: no cover - never reached, marks this as an async generator

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

    return _make


def _user(user_id: int, *, bot: bool = False) -> MagicMock:
    u = MagicMock()
    u.id = user_id
    u.bot = bot
    return u


@pytest.fixture
def patch_fetch_message(monkeypatch):
    """install a configurable replacement for auditor._fetch_discord_message"""

    def _install(return_value):
        async def _fake(*_a, **_kw):
            return return_value

        monkeypatch.setattr(auditor_mod, '_fetch_discord_message', _fake)

    return _install


class TestReconcileEntry:
    @pytest.mark.asyncio
    async def test_repos_not_initialized(self, task, monkeypatch):
        monkeypatch.setattr(ccboard, '_entry_repo', None)
        monkeypatch.setattr(ccboard, '_reaction_repo', None)

        result = await task.reconcile_entry(guild_id, message_id)
        assert isinstance(result, PassResult)
        assert result.mutated is False
        assert 'repos not initialized' in result.summary

    @pytest.mark.asyncio
    async def test_disabled_config(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.enabled = False

        result = await task.reconcile_entry(guild_id, message_id)
        assert result.mutated is False
        assert 'disabled' in result.summary

    @pytest.mark.asyncio
    async def test_no_emojis_configured(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.emojis = {}

        result = await task.reconcile_entry(guild_id, message_id)
        assert result.mutated is False
        assert 'emojis is empty' in result.summary

    @pytest.mark.asyncio
    async def test_missing_entry(self, task, make_guild_ccboard, entry_repo):
        entry_repo.get = AsyncMock(return_value=None)

        result = await task.reconcile_entry(guild_id, message_id)
        assert result.mutated is False
        assert 'no ccboard entry' in result.summary

    @pytest.mark.asyncio
    async def test_unfetchable_discord_message(self, task, make_guild_ccboard, patch_fetch_message):
        patch_fetch_message(None)

        result = await task.reconcile_entry(guild_id, message_id)
        assert result.mutated is False
        assert 'unavailable' in result.summary

    @pytest.mark.asyncio
    async def test_dry_run_summary_with_pending_diff(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo):
        """live has reactor_a/star, db empty: dry-run should report add=1 and not mutate"""
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[])

        result = await task.reconcile_entry(guild_id, message_id, dry_run=True)
        assert result.dry_run is True
        assert result.mutated is False
        assert 'add=1' in result.summary
        assert 'dry_run' in result.summary
        reaction_repo.upsert_active.assert_not_called()
        reaction_repo.soft_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_collapses_to_no_change_when_diff_empty(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo):
        """live and db match: dry_run False with no diff still returns mutated=False"""
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[_db_reaction(reactor_a, emoji_star)])

        result = await task.reconcile_entry(guild_id, message_id, dry_run=False)
        assert result.dry_run is True  # no_change collapses to dry_run path
        assert result.mutated is False
        reaction_repo.upsert_active.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_path_writes_and_marks_dirty(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo, entry_repo, stub_safe_remove):
        """dry_run=False with a real diff: upserts the new reaction, recomputes points, marks dirty"""
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[])
        reaction_repo.aggregate_points = AsyncMock(return_value=(1, 1))

        result = await task.reconcile_entry(guild_id, message_id, dry_run=False)
        assert result.dry_run is False
        assert result.mutated is True
        assert 'APPLIED' in result.summary
        reaction_repo.upsert_active.assert_awaited_once()
        reaction_repo.aggregate_points.assert_awaited_once_with(message_id)
        entry_repo.set_points.assert_awaited_once_with(message_id, net_points=1, positive_points=1)
        entry_repo.mark_dirty.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_apply_path_strips_bot_reactor_via_safe_remove(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo, stub_safe_remove):
        """bot reactor on live discord triggers _safe_remove_reaction during apply"""
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(bot_user_id, bot=True)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[])
        reaction_repo.aggregate_points = AsyncMock(return_value=(0, 0))

        await task.reconcile_entry(guild_id, message_id, dry_run=False)
        stub_safe_remove.assert_awaited()
        # nothing valid was added, so no upsert
        reaction_repo.upsert_active.assert_not_called()

    @pytest.mark.asyncio
    async def test_dry_run_reports_recount_when_weights_updated(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo):
        """live and db match but the db record predates weights_updated_at: dry-run reports recount=1, no mutation"""
        make_guild_ccboard.ccboard.weights_updated_at = 9_999_999_999
        stale_db = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None)
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[stale_db])

        result = await task.reconcile_entry(guild_id, message_id, dry_run=True)
        assert result.dry_run is True
        assert result.mutated is False
        assert 'recount=1' in result.summary
        assert 'match=0' in result.summary
        reaction_repo.upsert_active.assert_not_called()

    @pytest.mark.asyncio
    async def test_apply_path_recounts_stale_match_with_fresh_point_value(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo, entry_repo, stub_safe_remove):
        """confirm=True with a stale match: soft-delete + upsert under same emoji with current cfg point_value, last_recounted_at stamped"""
        # bump star weight to 5; existing record has point_value 1 from before the bump
        make_guild_ccboard.ccboard.emojis[emoji_star] = 5
        make_guild_ccboard.ccboard.weights_updated_at = 9_999_999_999
        stale_db = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None, point_value=1)
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[stale_db])
        reaction_repo.aggregate_points = AsyncMock(return_value=(5, 5))

        result = await task.reconcile_entry(guild_id, message_id, dry_run=False)

        assert result.mutated is True
        assert 'APPLIED' in result.summary
        assert 'recount=1' in result.summary
        # soft-delete called against the existing emoji
        reaction_repo.soft_delete.assert_awaited_once()
        # upsert called once with the new point_value
        upserted: ReactionDocument = reaction_repo.upsert_active.await_args.args[0]
        assert upserted.user_id == reactor_a
        assert upserted.emoji_str == emoji_star
        assert upserted.point_value == 5  # cfg.emojis[emoji_star] (5) + super_bonus * 0
        assert upserted.last_recounted_at is not None
        assert upserted.reacted_at == 100  # original reaction time preserved
        entry_repo.set_points.assert_awaited_once_with(message_id, net_points=5, positive_points=5)


class TestRecountEntryWrapper:
    """`recount_entry` is a thin wrapper around `reconcile_entry` that retags the kind."""

    @pytest.mark.asyncio
    async def test_returns_kind_recount_entry(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo):
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[])

        result = await task.recount_entry(guild_id, message_id, dry_run=True)
        assert result.kind == 'recount_entry'
        assert result.dry_run is True
        assert result.mutated is False

    @pytest.mark.asyncio
    async def test_propagates_apply_path_through_to_reconcile(self, task, make_guild_ccboard, fake_discord_msg, patch_fetch_message, reaction_repo, entry_repo, stub_safe_remove):
        """confirm=True via recount_entry should mutate identically to reconcile_entry"""
        make_guild_ccboard.ccboard.weights_updated_at = 9_999_999_999
        stale_db = _db_reaction(reactor_a, emoji_star, reacted_at=100, last_recounted_at=None, point_value=1)
        patch_fetch_message(fake_discord_msg([(emoji_star, [_user(reactor_a)], False)]))
        reaction_repo.list_for_message = AsyncMock(return_value=[stale_db])
        reaction_repo.aggregate_points = AsyncMock(return_value=(1, 1))

        result = await task.recount_entry(guild_id, message_id, dry_run=False)
        assert result.kind == 'recount_entry'
        assert result.mutated is True
        assert 'recount=1' in result.summary
        reaction_repo.upsert_active.assert_awaited_once()


# --- Singleton / scheduler-wiring guards ---


def test_singleton_is_audit_task():
    assert isinstance(auditor_task, AuditorTask)


def test_task_metadata_runs_manual_only():
    """interval=None and run_immediately=False keep the scheduler from firing run() on a timer."""
    assert auditor_task.interval is None
    assert auditor_task.run_immediately is False
    assert auditor_task.run_once is False
    assert auditor_task.name == 'CCBoardAuditor'


@pytest.mark.asyncio
async def test_run_is_a_no_op():
    await auditor_task.run()


# --- reconcile_guild tests (phase 2.4) ---


def _make_entry(msg_id: int) -> MagicMock:
    e = MagicMock()
    e.message_id = msg_id
    return e


class TestReconcileGuild:
    @pytest.mark.asyncio
    async def test_repos_not_initialized(self, task, monkeypatch):
        monkeypatch.setattr(ccboard, '_entry_repo', None)
        monkeypatch.setattr(ccboard, '_reaction_repo', None)
        result = await task.reconcile_guild(guild_id)
        assert result.kind == 'reconcile_guild'
        assert result.mutated is False
        assert 'repos not initialized' in result.summary

    @pytest.mark.asyncio
    async def test_disabled_config(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.enabled = False
        result = await task.reconcile_guild(guild_id)
        assert result.mutated is False
        assert 'disabled' in result.summary

    @pytest.mark.asyncio
    async def test_no_entries(self, task, make_guild_ccboard, entry_repo):
        entry_repo.all_for_guild = AsyncMock(return_value=[])
        result = await task.reconcile_guild(guild_id)
        assert result.kind == 'reconcile_guild'
        assert result.mutated is False
        assert 'no entries found' in result.summary

    @pytest.mark.asyncio
    async def test_iterates_all_entries_and_reports_processed(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """each entry triggers a reconcile_entry call; processed count matches"""
        e1, e2 = _make_entry(message_id), _make_entry(message_id + 1)
        entry_repo.all_for_guild = AsyncMock(return_value=[e1, e2])
        called_with = []

        async def fake_reconcile(gid, mid, *, dry_run=True):
            called_with.append(mid)
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary='no change')

        monkeypatch.setattr(task, 'reconcile_entry', fake_reconcile)
        result = await task.reconcile_guild(guild_id)
        assert set(called_with) == {message_id, message_id + 1}
        assert 'processed=2/2' in result.summary
        assert 'mutated=0' in result.summary
        assert 'skipped=0' in result.summary

    @pytest.mark.asyncio
    async def test_mutated_count_tracks_applied_entries(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        entry_repo.all_for_guild = AsyncMock(return_value=[_make_entry(message_id)])

        async def fake_reconcile(gid, mid, *, dry_run=True):
            return PassResult(kind='reconcile_entry', dry_run=False, mutated=True, summary='APPLIED')

        monkeypatch.setattr(task, 'reconcile_entry', fake_reconcile)
        result = await task.reconcile_guild(guild_id, dry_run=False)
        assert result.mutated is True
        assert 'mutated=1' in result.summary

    @pytest.mark.asyncio
    async def test_dry_run_propagated_to_each_entry(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        entry_repo.all_for_guild = AsyncMock(return_value=[_make_entry(message_id)])
        received_dry_run = []

        async def fake_reconcile(gid, mid, *, dry_run=True):
            received_dry_run.append(dry_run)
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary='ok')

        monkeypatch.setattr(task, 'reconcile_entry', fake_reconcile)
        await task.reconcile_guild(guild_id, dry_run=False)
        assert received_dry_run == [False]


# --- discover_guild tests (phase 2.4) ---


def _make_discord_msg_with_reactions(msg_id: int, emoji_strs: list[str]) -> MagicMock:
    msg = MagicMock()
    msg.id = msg_id
    reactions = []
    for es in emoji_strs:
        r = MagicMock()
        r.emoji = es
        reactions.append(r)
    msg.reactions = reactions
    return msg


def _make_board_msg(msg_id: int, author_id_val: int) -> MagicMock:
    """minimal fake Discord message for cleanup_orphans tests."""
    msg = MagicMock()
    msg.id = msg_id
    msg.author.id = author_id_val
    msg.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    msg.delete = AsyncMock()
    return msg


class _FakeChannel(discord.abc.Messageable):
    """minimal discord.abc.Messageable subclass for discover_guild tests."""

    def __init__(self, messages: list):
        self._messages = messages

    async def _get_channel(self):  # required by Messageable ABC
        return self

    def history(self, *args, **kwargs):
        async def _gen():
            for m in self._messages:
                yield m

        return _gen()


class TestDiscoverGuild:
    @pytest.mark.asyncio
    async def test_repos_not_initialized(self, task, monkeypatch):
        monkeypatch.setattr(ccboard, '_entry_repo', None)
        monkeypatch.setattr(ccboard, '_reaction_repo', None)
        result = await task.discover_guild(guild_id)
        assert result.kind == 'discover_guild'
        assert result.mutated is False
        assert 'repos not initialized' in result.summary

    @pytest.mark.asyncio
    async def test_disabled_config(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.enabled = False
        result = await task.discover_guild(guild_id)
        assert result.mutated is False
        assert 'disabled' in result.summary

    @pytest.mark.asyncio
    async def test_no_channels(self, task, make_guild_ccboard, entry_repo):
        entry_repo.distinct_channel_ids = AsyncMock(return_value=[])
        result = await task.discover_guild(guild_id)
        assert result.kind == 'discover_guild'
        assert result.mutated is False
        assert 'no channels' in result.summary

    @pytest.mark.asyncio
    async def test_dry_run_counts_untracked_without_creating(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """channel has one message with configured emoji and no db entry: dry_run reports found=1, mutated=False"""
        entry_repo.distinct_channel_ids = AsyncMock(return_value=[channel_id])
        entry_repo.get = AsyncMock(return_value=None)  # no existing entry

        msg = _make_discord_msg_with_reactions(message_id + 50, [emoji_star])
        mock_channel = _FakeChannel([msg])
        mock_bot = MagicMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.discover_guild(guild_id, dry_run=True)
        assert result.kind == 'discover_guild'
        assert result.dry_run is True
        assert result.mutated is False
        assert 'untracked=1' in result.summary
        assert 'would_create=0' in result.summary

    @pytest.mark.asyncio
    async def test_dry_run_skips_already_tracked_messages(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """message already in db: not counted as untracked"""
        from unittest.mock import MagicMock as MM

        entry_repo.distinct_channel_ids = AsyncMock(return_value=[channel_id])
        existing_entry = MM()
        entry_repo.get = AsyncMock(return_value=existing_entry)

        msg = _make_discord_msg_with_reactions(message_id, [emoji_star])
        mock_channel = _FakeChannel([msg])
        mock_bot = MagicMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.discover_guild(guild_id, dry_run=True)
        assert 'untracked=0' in result.summary
        assert result.mutated is False

    @pytest.mark.asyncio
    async def test_dry_run_skips_messages_without_configured_emoji(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """message has an emoji not in cfg.emojis: not counted"""
        entry_repo.distinct_channel_ids = AsyncMock(return_value=[channel_id])
        entry_repo.get = AsyncMock(return_value=None)

        msg = _make_discord_msg_with_reactions(message_id + 50, ['🍕'])  # not a configured emoji
        mock_channel = _FakeChannel([msg])
        mock_bot = MagicMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.discover_guild(guild_id, dry_run=True)
        assert 'untracked=0' in result.summary

    @pytest.mark.asyncio
    async def test_apply_creates_entry_via_ensure_entry(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """dry_run=False: calls _ensure_entry for untracked messages; created=1"""
        entry_repo.distinct_channel_ids = AsyncMock(return_value=[channel_id])
        entry_repo.get = AsyncMock(return_value=None)

        msg = _make_discord_msg_with_reactions(message_id + 50, [emoji_star])
        mock_channel = _FakeChannel([msg])
        mock_bot = MagicMock()
        mock_bot.get_channel = MagicMock(return_value=mock_channel)
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        created_entry = MagicMock()
        ensure_calls = []

        async def fake_ensure_entry(**kwargs):
            ensure_calls.append(kwargs)
            return created_entry

        import nova_core.ccboard.watcher as watcher_mod_ref

        monkeypatch.setattr(watcher_mod_ref, '_ensure_entry', fake_ensure_entry)

        result = await task.discover_guild(guild_id, dry_run=False)
        assert result.mutated is True
        assert 'created=1' in result.summary
        assert len(ensure_calls) == 1
        assert ensure_calls[0]['real_message_id'] == message_id + 50
        assert ensure_calls[0]['guild_id'] == guild_id

    @pytest.mark.asyncio
    async def test_unavailable_channel_is_skipped(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """channel fetch fails: channel is skipped, scan continues with the next one"""
        entry_repo.distinct_channel_ids = AsyncMock(return_value=[channel_id, channel_id + 1])
        entry_repo.get = AsyncMock(return_value=None)

        msg = _make_discord_msg_with_reactions(message_id + 50, [emoji_star])
        good_channel = _FakeChannel([msg])

        mock_bot = MagicMock()

        def get_channel_side_effect(cid):
            return None  # force fetch_channel path

        async def fetch_channel_side_effect(cid):
            if cid == channel_id:
                raise discord.NotFound(MagicMock(), 'not found')
            return good_channel

        mock_bot.get_channel = MagicMock(side_effect=get_channel_side_effect)
        mock_bot.fetch_channel = AsyncMock(side_effect=fetch_channel_side_effect)
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.discover_guild(guild_id, dry_run=True)
        # only the good channel was scanned; one untracked message found
        assert result.kind == 'discover_guild'
        assert 'channels=1' in result.summary
        assert 'untracked=1' in result.summary


class TestCleanupOrphans:
    @pytest.fixture
    def task(self):
        return AuditorTask()

    @pytest.mark.asyncio
    async def test_repos_not_initialized(self, task, monkeypatch):
        monkeypatch.setattr(ccboard, '_entry_repo', None)
        monkeypatch.setattr(ccboard, '_reaction_repo', None)
        result = await task.cleanup_orphans(guild_id)
        assert result.kind == 'cleanup_orphans'
        assert result.mutated is False
        assert 'repos not initialized' in result.summary

    @pytest.mark.asyncio
    async def test_disabled_config(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.enabled = False
        result = await task.cleanup_orphans(guild_id)
        assert 'ccboard disabled' in result.summary

    @pytest.mark.asyncio
    async def test_no_channel_configured(self, task, make_guild_ccboard):
        make_guild_ccboard.ccboard.channel_id = 0
        result = await task.cleanup_orphans(guild_id)
        assert 'channel_id not configured' in result.summary

    @pytest.mark.asyncio
    async def test_dry_run_detects_orphans(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """bot message with no DB twin older than grace period: reported as orphan candidate"""
        orphan_msg = _make_board_msg(message_id + 100, bot_user_id)
        entry_repo.get_by_starboard_message = AsyncMock(return_value=None)

        mock_bot = MagicMock()
        mock_bot.user.id = bot_user_id
        mock_bot.get_channel = MagicMock(return_value=_FakeChannel([orphan_msg]))
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.cleanup_orphans(guild_id, dry_run=True)
        assert result.kind == 'cleanup_orphans'
        assert result.mutated is False
        assert 'orphans=1' in result.summary
        assert 'would_delete=0' in result.summary

    @pytest.mark.asyncio
    async def test_skips_non_bot_messages(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """messages not authored by the bot are ignored regardless of DB state"""
        user_msg = _make_board_msg(message_id + 101, reactor_a)
        entry_repo.get_by_starboard_message = AsyncMock(return_value=None)

        mock_bot = MagicMock()
        mock_bot.user.id = bot_user_id
        mock_bot.get_channel = MagicMock(return_value=_FakeChannel([user_msg]))
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.cleanup_orphans(guild_id, dry_run=True)
        assert 'orphans=0' in result.summary

    @pytest.mark.asyncio
    async def test_skips_messages_with_db_twin(self, task, make_guild_ccboard, entry_doc, entry_repo, monkeypatch):
        """bot message that has a DB twin is not an orphan"""
        tracked_msg = _make_board_msg(message_id + 102, bot_user_id)
        entry_repo.get_by_starboard_message = AsyncMock(return_value=entry_doc)

        mock_bot = MagicMock()
        mock_bot.user.id = bot_user_id
        mock_bot.get_channel = MagicMock(return_value=_FakeChannel([tracked_msg]))
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.cleanup_orphans(guild_id, dry_run=True)
        assert 'orphans=0' in result.summary

    @pytest.mark.asyncio
    async def test_apply_deletes_orphan(self, task, make_guild_ccboard, entry_repo, monkeypatch):
        """dry_run=False: orphan is deleted from Discord and deleted=1 reported"""
        orphan_msg = _make_board_msg(message_id + 103, bot_user_id)
        entry_repo.get_by_starboard_message = AsyncMock(return_value=None)

        mock_bot = MagicMock()
        mock_bot.user.id = bot_user_id
        mock_bot.get_channel = MagicMock(return_value=_FakeChannel([orphan_msg]))
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.cleanup_orphans(guild_id, dry_run=False)
        assert result.mutated is True
        assert 'deleted=1' in result.summary
        orphan_msg.delete.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_channel_unavailable(self, task, make_guild_ccboard, monkeypatch):
        """ccboard channel fetch fails: returns a Failed summary"""
        mock_bot = MagicMock()
        mock_bot.user.id = bot_user_id
        mock_bot.get_channel = MagicMock(return_value=None)
        mock_bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(MagicMock(), 'not found'))
        monkeypatch.setattr(auditor_mod, '_get_bot', lambda: mock_bot)

        result = await task.cleanup_orphans(guild_id)
        assert 'Failed' in result.summary
        assert 'unavailable' in result.summary


def test_manifest_tasks_includes_auditor():
    """ccboard auditor is now registered via FeatureManifest.tasks, not register_bot_tasks."""
    import nova_core.ccboard as ccboard_mod

    task_names = {t.name for t in ccboard_mod.manifest.tasks}
    assert 'CCBoardAuditor' in task_names


def test_manifest_tasks_has_exactly_one_auditor():
    """manifest.tasks must declare the auditor exactly once."""
    import nova_core.ccboard as ccboard_mod

    auditor_count = sum(1 for t in ccboard_mod.manifest.tasks if t.name == 'CCBoardAuditor')
    assert auditor_count == 1
