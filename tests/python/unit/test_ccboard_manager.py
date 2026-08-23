# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_manager | unit tests for the ccboard manager task."""

from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest

from attu_models import MessageAuthor, MessageContent, MessageDocument, MessageRefs
from nova_core.ccboard.documents import BoardEntryDocument
from nova_core.ccboard.manager import ManagerTask, _lowest_positive_emoji, _sweep_message
from nova_core.config import GuildCCBoard


# --- constants ---

guild_id = 1234567890
channel_id = 5555555555
ccboard_channel_id = 4444444444
message_id = 111000111000111000
post_id = 222000222000222000
new_post_id = 333000333000333000
author_id = 573360359566737409


# --- fixtures ---


@pytest.fixture(autouse=True)
def _stub_bot(monkeypatch):
    """stub nova_core.client.core.bot for builder + manager"""

    class _StubBot:
        def get_user(self, _user_id):
            return None

        def get_channel(self, _channel_id):
            return None

        async def fetch_channel(self, _channel_id):
            return None

    import nova_core.client.core as core_module

    monkeypatch.setattr(core_module, 'bot', _StubBot(), raising=False)


def _make_msg() -> MessageDocument:
    return MessageDocument(
        message_id=message_id,
        guild_id=guild_id,
        channel_id=channel_id,
        author=MessageAuthor(id=author_id, name='TestUser', bot=False),
        content=MessageContent(text='hello world'),
        refs=MessageRefs(),
        created_at=1704067200,
    )


def _make_entry(
    *,
    starboard_message_id: int | None = None,
    positive_points: int = 4,
    net_points: int = 4,
    reply_created: bool = False,
    effective_author_id: int | None = None,
) -> BoardEntryDocument:
    return BoardEntryDocument(
        message_id=message_id,
        channel_id=channel_id,
        guild_id=guild_id,
        author_id=author_id,
        effective_author_id=effective_author_id,
        starboard_message_id=starboard_message_id,
        net_points=net_points,
        positive_points=positive_points,
        reply_created=reply_created,
        snapshot=_make_msg(),
    )


def _make_cfg(**overrides) -> GuildCCBoard:
    defaults = {
        'enabled': True,
        'channel_id': ccboard_channel_id,
        'emojis': {'⭐': 1, '✨': 2, '💀': -1},
        'super_bonus': 1,
        'threshold': 2,
        'points_label': 'stars',
        'positive_color': '#EEDD20',
        'negative_color': '#DD2020',
    }
    defaults.update(overrides)
    return GuildCCBoard(**defaults)


def _patched_repo() -> MagicMock:
    """build a mock entry repo with the methods the manager calls"""
    repo = MagicMock()
    repo.set_starboard_message = AsyncMock()
    repo.set_reply_created = AsyncMock()
    repo.mark_synced = AsyncMock()
    repo.recent_authors = AsyncMock(return_value=[])
    repo.find_settled = AsyncMock(return_value=[])
    return repo


def _patched_channel() -> MagicMock:
    """build a mock discord channel returning controllable partial messages"""
    channel = MagicMock()
    channel.send = AsyncMock()
    channel.get_partial_message = MagicMock()
    return channel


def _stub_get_channel(channel) -> MagicMock:
    """build a bot mock whose get_channel returns the supplied channel"""
    bot = MagicMock()
    bot.get_channel = MagicMock(return_value=channel)
    bot.fetch_channel = AsyncMock(return_value=channel)
    return bot


# --- helper tests ---


def test_lowest_positive_emoji_picks_smallest_positive():
    cfg = _make_cfg(emojis={'⭐': 1, '✨': 2, '💀': -1})
    assert _lowest_positive_emoji(cfg) == '⭐'


def test_lowest_positive_emoji_returns_none_when_no_positives():
    cfg = _make_cfg(emojis={'💀': -1})
    assert _lowest_positive_emoji(cfg) is None


def test_sweep_message_only_at_3_5_11():
    assert _sweep_message(2, author_id) is None
    assert _sweep_message(3, author_id) is not None
    assert _sweep_message(4, author_id) is None
    assert _sweep_message(5, author_id) is not None
    assert _sweep_message(11, author_id) is not None
    assert _sweep_message(12, author_id) is None


def test_sweep_message_text_contains_user_mention():
    text = _sweep_message(3, author_id)
    assert text is not None
    assert f'<@{author_id}>' in text
    assert 'sweaps' in text


# --- _sync_post tests ---


@pytest.mark.asyncio
async def test_below_threshold_with_post_deletes_and_clears():
    """positive_points < threshold and a post exists -> delete the post and clear the reference"""
    entry = _make_entry(starboard_message_id=post_id, positive_points=1, net_points=1)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    partial = MagicMock()
    partial.delete = AsyncMock()
    channel.get_partial_message.return_value = partial

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    partial.delete.assert_awaited_once()
    repo.set_starboard_message.assert_awaited_once_with(message_id, None)


@pytest.mark.asyncio
async def test_below_threshold_no_post_does_nothing():
    """positive_points < threshold and no post -> nothing to do"""
    entry = _make_entry(starboard_message_id=None, positive_points=1, net_points=1)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    repo.set_starboard_message.assert_not_called()
    channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_above_threshold_no_post_creates_post():
    """positive_points >= threshold and no post -> build embeds, send, store id, react"""
    entry = _make_entry(starboard_message_id=None, positive_points=4, net_points=4)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    sent = MagicMock()
    sent.id = new_post_id
    sent.add_reaction = AsyncMock()
    sent.delete = AsyncMock()
    channel.send.return_value = sent

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    channel.send.assert_awaited_once()
    repo.set_starboard_message.assert_awaited_once_with(message_id, new_post_id)
    sent.add_reaction.assert_awaited_once_with('⭐')


@pytest.mark.asyncio
async def test_above_threshold_post_exists_edits_in_place():
    """positive_points >= threshold and post exists -> edit existing"""
    entry = _make_entry(starboard_message_id=post_id, positive_points=4, net_points=4)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    partial = MagicMock()
    partial.edit = AsyncMock()
    channel.get_partial_message.return_value = partial

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    partial.edit.assert_awaited_once()
    channel.send.assert_not_called()
    repo.set_starboard_message.assert_not_called()


@pytest.mark.asyncio
async def test_edit_not_found_clears_and_recreates():
    """discord.NotFound on edit -> clear starboard_message_id and create a new post"""
    entry = _make_entry(starboard_message_id=post_id, positive_points=4, net_points=4)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    partial = MagicMock()
    partial.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(status=404), 'gone'))
    channel.get_partial_message.return_value = partial

    new_msg = MagicMock()
    new_msg.id = new_post_id
    new_msg.add_reaction = AsyncMock()
    new_msg.delete = AsyncMock()
    channel.send.return_value = new_msg

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    # cleared once for the not-found, set again on create
    set_calls = [call.args for call in repo.set_starboard_message.await_args_list]
    assert (message_id, None) in set_calls
    assert (message_id, new_post_id) in set_calls
    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_db_write_failure_deletes_orphan():
    """post-create db write fails -> delete the orphan discord message and re-raise"""
    entry = _make_entry(starboard_message_id=None, positive_points=4, net_points=4)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    repo.set_starboard_message.side_effect = RuntimeError('db down')
    channel = _patched_channel()
    sent = MagicMock()
    sent.id = new_post_id
    sent.add_reaction = AsyncMock()
    sent.delete = AsyncMock()
    channel.send.return_value = sent

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot), pytest.raises(RuntimeError):
        await task._sync_post(entry, cfg)

    sent.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_edit_forbidden_sends_reply():
    """discord.Forbidden on edit and no prior reply -> send reply, mark reply_created"""
    entry = _make_entry(starboard_message_id=post_id, positive_points=4, net_points=4, reply_created=False)
    cfg = _make_cfg(threshold=2)

    repo = _patched_repo()
    channel = _patched_channel()
    partial = MagicMock()
    partial.edit = AsyncMock(side_effect=discord.Forbidden(MagicMock(status=403), 'no'))
    channel.get_partial_message.return_value = partial

    new_msg = MagicMock()
    new_msg.id = new_post_id
    new_msg.add_reaction = AsyncMock()
    channel.send.return_value = new_msg

    bot = _stub_get_channel(channel)
    task = ManagerTask()

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._sync_post(entry, cfg)

    channel.send.assert_awaited_once()
    repo.set_starboard_message.assert_any_await(message_id, new_post_id)
    repo.set_reply_created.assert_awaited_once_with(message_id)


# --- sweep tests ---


@pytest.mark.asyncio
async def test_sweep_at_3_sends_announcement():
    """credited author has streak of exactly 3 -> sweep embed sent"""
    entry = _make_entry(starboard_message_id=None, positive_points=4)
    cfg = _make_cfg()

    repo = _patched_repo()
    repo.recent_authors.return_value = [author_id, author_id, author_id, 999, 888]
    channel = _patched_channel()
    channel.send.return_value = MagicMock(id=new_post_id, add_reaction=AsyncMock(), delete=AsyncMock())

    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    # one send for the sweep embed
    channel.send.assert_awaited_once()
    kwargs = channel.send.await_args.kwargs
    assert 'embed' in kwargs
    sent_embed = kwargs['embed']
    assert isinstance(sent_embed, discord.Embed)
    assert sent_embed.description is not None
    assert 'sweaps' in sent_embed.description


@pytest.mark.asyncio
async def test_sweep_at_5_sends_announcement():
    entry = _make_entry()
    cfg = _make_cfg()
    repo = _patched_repo()
    repo.recent_authors.return_value = [author_id] * 5 + [999]
    channel = _patched_channel()
    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_at_11_sends_announcement():
    entry = _make_entry()
    cfg = _make_cfg()
    repo = _patched_repo()
    repo.recent_authors.return_value = [author_id] * 11 + [999]
    channel = _patched_channel()
    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    channel.send.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_at_4_does_not_send():
    """streak of 4 (not 3/5/11) -> no announcement"""
    entry = _make_entry()
    cfg = _make_cfg()
    repo = _patched_repo()
    repo.recent_authors.return_value = [author_id, author_id, author_id, author_id, 999]
    channel = _patched_channel()
    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_streak_interrupted_no_announcement():
    """another author appears mid-streak -> streak resets, no announcement"""
    entry = _make_entry()
    cfg = _make_cfg()
    repo = _patched_repo()
    # newest first: self, self, OTHER -> streak only counts the leading run -> 2
    repo.recent_authors.return_value = [author_id, author_id, 999, author_id, author_id, author_id]
    channel = _patched_channel()
    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_sweep_swallows_exceptions():
    """recent_authors raises -> no propagation, no send"""
    entry = _make_entry()
    cfg = _make_cfg()
    repo = _patched_repo()
    repo.recent_authors.side_effect = RuntimeError('db down')
    channel = _patched_channel()
    task = ManagerTask()
    bot = _stub_get_channel(channel)

    with patch('nova_core.ccboard.manager._get_entry_repo', return_value=repo), patch('nova_core.client.core.bot', bot):
        await task._announce_sweep(entry, cfg, channel)

    channel.send.assert_not_called()


# --- registration test ---
# mock-compensation: register_bot_tasks is mocked in other tests by replacing the scheduler;
# this real-call test verifies the manager singleton is wired into the task list.


def test_manifest_tasks_includes_manager():
    """ccboard manager is now registered via FeatureManifest.tasks, not register_bot_tasks."""
    import nova_core.ccboard as ccboard_mod
    from nova_core.ccboard.manager import manager_task as ccboard_manager_task

    assert ccboard_manager_task in ccboard_mod.manifest.tasks


def test_register_bot_tasks_idempotent():
    """calling twice doesn't re-register the manager"""
    from nova_core.ccboard.manager import manager_task as ccboard_manager_task
    from nova_core.tasks import register_bot_tasks

    scheduler = MagicMock()
    scheduler.registered_tasks = MagicMock(return_value=[ccboard_manager_task])
    scheduler.register = MagicMock()

    register_bot_tasks(scheduler)

    registered = [call.args[0] for call in scheduler.register.call_args_list]
    assert ccboard_manager_task not in registered
