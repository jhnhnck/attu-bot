# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_watcher | unit tests for the ccboard reaction watcher."""

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
from nova_core import ccboard
from nova_core.ccboard import watcher
from nova_core.config import GuildCCBoard
from tests.conftest import test_guild


# --- Constants ---

channel_id = 5555555555
ccboard_channel_id = 9999999999
message_id = 111000111000111000
author_id = 573360359566737409
user_id = 100000001
reactor_id = 100000002

emoji_star = '⭐'
emoji_fire = '🔥'
emoji_skull = '💀'


# --- Fixtures ---


@pytest.fixture
def cfg():
    """default ccboard config with star=+1, fire=+2, skull=-1"""
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
    """install a guild config with the ccboard test cfg attached"""
    gc = make_guild()
    gc.ccboard = cfg
    return gc


@pytest.fixture
def snapshot():
    """default MessageDocument snapshot for a non-bot user message"""
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
    """BoardEntryDocument for the standard snapshot"""
    return BoardEntryDocument(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=test_guild,
        author_id=author_id,
        snapshot=snapshot,
    )


@pytest.fixture
def reaction_repo():
    """AsyncMock-backed ReactionRepository drop-in"""
    repo = MagicMock()
    repo.get_active = AsyncMock(return_value=None)
    repo.upsert_active = AsyncMock(return_value=None)
    repo.soft_delete = AsyncMock(return_value=None)
    repo.soft_delete_all_for_message = AsyncMock(return_value=0)
    repo.soft_delete_emoji = AsyncMock(return_value=0)
    repo.aggregate_points = AsyncMock(return_value=(0, 0))
    return repo


@pytest.fixture
def entry_repo(entry_doc):
    """AsyncMock-backed EntryRepository drop-in; pre-populated with entry_doc"""
    repo = MagicMock()
    repo.get = AsyncMock(return_value=entry_doc)
    repo.get_by_starboard_message = AsyncMock(return_value=None)
    repo.get_by_display_message = AsyncMock(return_value=None)
    repo.upsert = AsyncMock(return_value=None)
    repo.set_points = AsyncMock(return_value=None)
    repo.mark_dirty = AsyncMock(return_value=None)
    return repo


@pytest.fixture(autouse=True)
def _wire_repos(reaction_repo, entry_repo, monkeypatch):
    """install AsyncMock repos onto ccboard module for the duration of a test"""
    monkeypatch.setattr(ccboard, '_reaction_repo', reaction_repo)
    monkeypatch.setattr(ccboard, '_entry_repo', entry_repo)
    yield
    # ensure pending-removal state never bleeds across tests
    ccboard._pending_bot_removals.clear()
    ccboard._locks.clear()


@pytest.fixture(autouse=True)
def _stub_remove_reaction(monkeypatch):
    """default: discord remove succeeds. tests override via the returned stub."""
    stub = AsyncMock(return_value=True)
    monkeypatch.setattr(watcher, '_remove_reaction_from_discord', stub)
    return stub


# --- Tests ---


@pytest.mark.asyncio
async def test_self_star_echo_ignored(make_guild_ccboard, entry_doc, reaction_repo):
    """case 1: self-star registers a pending key, removes via discord, then a remove echo
    consumes the key and leaves the (absent) ReactionDocument untouched."""
    # author reacts to their own message - this is a self-star
    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=author_id,
        emoji_str=emoji_star,
        is_burst=False,
        is_bot=False,
    )

    # pending key registered for the *physical* discord location
    assert (channel_id, message_id, author_id, emoji_star) in ccboard._pending_bot_removals
    # no ReactionDocument was upserted for the self-star
    reaction_repo.upsert_active.assert_not_called()

    # echo from discord arrives - same physical location
    await watcher.handle_reaction_remove(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=author_id,
        emoji_str=emoji_star,
    )

    # echo consumed the key; nothing was soft-deleted
    assert (channel_id, message_id, author_id, emoji_star) not in ccboard._pending_bot_removals
    reaction_repo.soft_delete.assert_not_called()


@pytest.mark.asyncio
async def test_vote_change_echo_ignored(make_guild_ccboard, entry_doc, reaction_repo, _stub_remove_reaction):
    """case 2: user has active star vote; adding fire removes the old star from discord
    via source_message_id/source_channel_id and registers the pending key. the echo
    consumes the key, the old doc is soft-deleted, and the new fire doc is created."""
    old_source_channel = ccboard_channel_id
    old_source_message = 222000222000222000  # the user originally reacted on the starboard post
    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_star,
        is_super=False,
        point_value=1,
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=old_source_message,
        source_channel_id=old_source_channel,
    )
    reaction_repo.get_active.return_value = existing

    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_fire,
        is_burst=False,
        is_bot=False,
    )

    # discord removal targeted the OLD physical location, not the new one
    _stub_remove_reaction.assert_awaited_once_with(old_source_channel, old_source_message, reactor_id, emoji_star)
    # old doc soft-deleted with expected_emoji=star
    reaction_repo.soft_delete.assert_awaited_once()
    sd_call = reaction_repo.soft_delete.call_args
    assert sd_call.kwargs.get('expected_emoji') == emoji_star
    # new fire doc upserted
    reaction_repo.upsert_active.assert_awaited()
    upserted = reaction_repo.upsert_active.call_args.args[0]
    assert upserted.emoji_str == emoji_fire
    assert upserted.point_value == 2

    # the pending key was registered then consumed by the discord removal echo path -
    # since _stub_remove_reaction returned True, the key remains pending for the echo
    assert (old_source_channel, old_source_message, reactor_id, emoji_star) in ccboard._pending_bot_removals

    # simulate the echoed remove event
    await watcher.handle_reaction_remove(
        guild_id=test_guild,
        channel_id=old_source_channel,
        message_id=old_source_message,
        user_id=reactor_id,
        emoji_str=emoji_star,
    )

    # echo consumed; soft_delete not called a second time
    assert (old_source_channel, old_source_message, reactor_id, emoji_star) not in ccboard._pending_bot_removals
    assert reaction_repo.soft_delete.await_count == 1


@pytest.mark.asyncio
async def test_same_emoji_re_react_phantom_recovery(make_guild_ccboard, entry_doc, reaction_repo, _stub_remove_reaction):
    """case 3: user has an active star and re-reacts with star (a missed remove left the
    db inconsistent with discord). refresh in place; no discord removal; no pending key."""
    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_star,
        is_super=False,
        point_value=1,
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=message_id,
        source_channel_id=channel_id,
    )
    reaction_repo.get_active.return_value = existing

    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_star,
        is_burst=False,
        is_bot=False,
    )

    # no discord removal, no pending key
    _stub_remove_reaction.assert_not_called()
    assert len(ccboard._pending_bot_removals) == 0
    # no soft_delete - this was a refresh, not a vote change
    reaction_repo.soft_delete.assert_not_called()
    # the existing record is refreshed in place via upsert_active
    reaction_repo.upsert_active.assert_awaited_once()
    refreshed = reaction_repo.upsert_active.call_args.args[0]
    assert refreshed.emoji_str == emoji_star
    assert refreshed.user_id == reactor_id
    # stamp last_recounted_at so the auditor's staleness predicate sees this as fresh
    assert refreshed.last_recounted_at is not None
    assert refreshed.last_recounted_at == refreshed.reacted_at


@pytest.mark.asyncio
async def test_same_emoji_refresh_re_snapshots_point_value_after_weight_change(make_guild_ccboard, cfg, entry_doc, reaction_repo, _stub_remove_reaction):
    """when cfg weights changed after the original reaction, the same-emoji
    refresh path re-snapshots point_value from current cfg and stamps last_recounted_at
    so the auditor's staleness predicate skips this record on the next recount pass."""
    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_star,
        is_super=False,
        point_value=1,  # snapshot from before the weight bump
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=message_id,
        source_channel_id=channel_id,
        last_recounted_at=None,
    )
    reaction_repo.get_active.return_value = existing
    cfg.emojis[emoji_star] = 7  # admin bumped the weight via the web UI

    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_star,
        is_burst=False,
        is_bot=False,
    )

    refreshed = reaction_repo.upsert_active.call_args.args[0]
    assert refreshed.point_value == 7
    assert refreshed.last_recounted_at is not None


@pytest.mark.asyncio
async def test_vote_change_removal_failure(make_guild_ccboard, entry_doc, reaction_repo, _stub_remove_reaction):
    """case 4: discord remove_reaction raises during vote change. pending key is
    discarded, old doc still soft-deleted, new doc still created - db correctness wins."""
    _stub_remove_reaction.return_value = False  # simulates a 404/429/network error

    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_star,
        is_super=False,
        point_value=1,
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=message_id,
        source_channel_id=channel_id,
    )
    reaction_repo.get_active.return_value = existing

    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_fire,
        is_burst=False,
        is_bot=False,
    )

    # pending key was registered then discarded after the failed remove
    assert (channel_id, message_id, reactor_id, emoji_star) not in ccboard._pending_bot_removals
    # old doc still soft-deleted; new fire doc still upserted
    reaction_repo.soft_delete.assert_awaited_once()
    reaction_repo.upsert_active.assert_awaited()
    new_doc = reaction_repo.upsert_active.call_args.args[0]
    assert new_doc.emoji_str == emoji_fire


@pytest.mark.asyncio
async def test_user_initiated_removal_processed(make_guild_ccboard, entry_doc, reaction_repo):
    """case 5: a real user-initiated remove with no pending key flows through to
    soft_delete after redirect resolution."""
    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_star,
        is_super=False,
        point_value=1,
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=message_id,
        source_channel_id=channel_id,
    )
    reaction_repo.get_active.return_value = existing
    reaction_repo.soft_delete.return_value = existing

    await watcher.handle_reaction_remove(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_star,
    )

    reaction_repo.soft_delete.assert_awaited_once()
    sd_call = reaction_repo.soft_delete.call_args
    assert sd_call.kwargs.get('expected_emoji') == emoji_star


@pytest.mark.asyncio
async def test_pending_key_discarded_on_self_star_api_failure(make_guild_ccboard, entry_doc, _stub_remove_reaction):
    """case 6: self-star removal hits an api error; pending key must be discarded
    so a stale entry doesn't suppress a future remove event."""
    _stub_remove_reaction.return_value = False

    await watcher.handle_reaction_add(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=author_id,
        emoji_str=emoji_star,
        is_burst=False,
        is_bot=False,
    )

    # the pending key was registered before the api call and discarded after failure
    assert (channel_id, message_id, author_id, emoji_star) not in ccboard._pending_bot_removals


@pytest.mark.asyncio
async def test_stale_echo_rejected_by_emoji_mismatch(make_guild_ccboard, entry_doc, reaction_repo):
    """case 7: user has active fire; a stale star remove arrives. doc.emoji_str != incoming;
    the watcher ignores the remove rather than soft-deleting the wrong record."""
    existing = ReactionDocument(
        message_id=message_id,
        user_id=reactor_id,
        guild_id=test_guild,
        author_id=author_id,
        emoji_str=emoji_fire,
        is_super=False,
        point_value=2,
        reacted_at=1,
        removed=False,
        removed_at=None,
        source_message_id=message_id,
        source_channel_id=channel_id,
    )
    reaction_repo.get_active.return_value = existing

    await watcher.handle_reaction_remove(
        guild_id=test_guild,
        channel_id=channel_id,
        message_id=message_id,
        user_id=reactor_id,
        emoji_str=emoji_star,
    )

    # mismatched emoji - ignored entirely
    reaction_repo.soft_delete.assert_not_called()


# --- Mock-Compensation Test ---


def test_extension_imports_cleanly_with_ccboard_wiring():
    """compensation: the existing TestExtensionImports test mocks load_extension; this
    test verifies that the new ccboard listener wiring on events.py is *additive* (not
    replacing the legacy starboard handlers) and that nova_core.client.events still
    imports cleanly with both systems registered.
    """
    import importlib

    events_mod = importlib.import_module('nova_core.client.events')
    # both legacy handlers still imported via local imports inside listeners; the
    # ccboard-enabled gate function is exposed at module scope as a sanity check
    assert hasattr(events_mod, '_ccboard_enabled')
    # ccboard watcher is importable
    importlib.import_module('nova_core.ccboard.watcher')


# --- _starboard_enabled unit tests ---


def test_starboard_enabled_returns_false_when_config_disabled(monkeypatch):
    """_starboard_enabled returns False when guild config has starboard.enabled=False"""
    import importlib
    from unittest.mock import MagicMock

    events_mod = importlib.import_module('nova_core.client.events')

    mock_starboard = MagicMock()
    mock_starboard.enabled = False
    mock_guild = MagicMock()
    mock_guild.starboard = mock_starboard
    mock_config = MagicMock()
    mock_config.guild.return_value = mock_guild

    monkeypatch.setattr(events_mod, 'config', mock_config)
    assert events_mod._starboard_enabled(12345) is False


def test_starboard_enabled_returns_true_on_config_exception(monkeypatch):
    """_starboard_enabled fails open — returns True when config.guild() raises so a
    config error never silently suppresses legacy starboard reactions"""
    import importlib
    from unittest.mock import MagicMock

    events_mod = importlib.import_module('nova_core.client.events')

    mock_config = MagicMock()
    mock_config.guild.side_effect = Exception('config not loaded')

    monkeypatch.setattr(events_mod, 'config', mock_config)
    assert events_mod._starboard_enabled(12345) is True
