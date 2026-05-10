# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_auditor | unit tests for the ccboard auditor task.

phase 2.2 implementation: covers `_compute_diff` (pure) and `reconcile_entry`
(mocked end-to-end). later-phase passes (recount, discover, cleanup_orphans)
remain stubs and are exercised at the PassResult-shape level only.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from attu_models import (
    BoardEntryDocument,
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    ReactionDocument,
)
from doom_bot import ccboard
from doom_bot.ccboard import auditor as auditor_mod
from doom_bot.ccboard import watcher as watcher_mod
from doom_bot.ccboard.auditor import (
    AuditorTask,
    PassResult,
    _compute_diff,
    _LiveReaction,
    auditor_task,
)
from doom_bot.config import GuildCCBoard
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


def _db_reaction(user_id: int, emoji: str, *, is_super: bool = False, point_value: int = 1) -> ReactionDocument:
    return ReactionDocument(
        message_id=message_id,
        user_id=user_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji,
        is_super=is_super,
        point_value=point_value,
        reacted_at=1704067200,
        source_message_id=message_id,
        source_channel_id=channel_id,
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


# --- Pass stubs that have not yet been implemented ---


@pytest.mark.asyncio
async def test_reconcile_guild_returns_stub():
    result = await auditor_task.reconcile_guild(guild_id)
    assert result.kind == 'reconcile_guild'
    assert result.dry_run is True
    assert result.mutated is False
    assert 'phase 2.4' in result.summary


@pytest.mark.asyncio
async def test_recount_entry_advertises_phase_dependency():
    result = await auditor_task.recount_entry(guild_id, message_id)
    assert result.kind == 'recount_entry'
    assert 'phase 2.3' in result.summary
    assert result.mutated is False


@pytest.mark.asyncio
async def test_discover_guild_returns_stub():
    result = await auditor_task.discover_guild(guild_id)
    assert result.kind == 'discover_guild'
    assert result.dry_run is True
    assert result.mutated is False


@pytest.mark.asyncio
async def test_cleanup_orphans_advertises_grace_period():
    result = await auditor_task.cleanup_orphans(guild_id, grace_days=14)
    assert result.kind == 'cleanup_orphans'
    assert result.dry_run is True
    assert '14d' in result.summary
    assert result.mutated is False


def test_register_bot_tasks_includes_auditor():
    from doom_bot.tasks import register_bot_tasks
    from doom_bot.tasks.scheduler import TaskScheduler

    scheduler = TaskScheduler()
    register_bot_tasks(scheduler)
    registered_names = {task.name for task in scheduler.registered_tasks()}
    assert 'CCBoardAuditor' in registered_names


def test_register_bot_tasks_is_idempotent_for_auditor():
    from doom_bot.tasks import register_bot_tasks
    from doom_bot.tasks.scheduler import TaskScheduler

    scheduler = TaskScheduler()
    register_bot_tasks(scheduler)
    register_bot_tasks(scheduler)
    auditor_count = sum(1 for task in scheduler.registered_tasks() if task.name == 'CCBoardAuditor')
    assert auditor_count == 1
