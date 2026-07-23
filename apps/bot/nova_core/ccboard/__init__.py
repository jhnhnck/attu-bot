# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard | reaction-board package shared state."""

import asyncio
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from attu_models import EntryRepository, ReactionRepository


# repository singletons populated by nova_core.database._wire_repos at startup.
# the watcher and manager read these at call time; importing them at module scope
# would race with init_database().
_reaction_repo: 'ReactionRepository | None' = None
_entry_repo: 'EntryRepository | None' = None


# per-message asyncio locks shared by the watcher and manager so reaction events,
# the manager's _sync_post, and migration / fix commands serialize on the same key.
# the lock dict is keyed on the *resolved* message_id (after redirect from a board post
# or /stars display message), so all routes converge on one lock per original message.
_locks: dict[int, asyncio.Lock] = {}


def get_lock(message_id: int) -> asyncio.Lock:
    """return (creating if needed) the asyncio.Lock for one message"""
    lock = _locks.get(message_id)
    if lock is None:
        lock = asyncio.Lock()
        _locks[message_id] = lock
    return lock


# bot-removal echo suppression.
# whenever the watcher triggers discord.Message.remove_reaction itself, it must register
# a key here *before* the api call and consume it in handle_reaction_remove so the echoed
# raw_reaction_remove event is ignored. without this, the echo would soft-delete the user's
# active ReactionDocument or cascade through the redirect chain.
# key shape: (channel_id, message_id, user_id, emoji_str) — these are the values from
# the echoed payload, which carries the *user's* id, not the bot's.
_pending_bot_removals: set[tuple[int, int, int, str]] = set()


def register_pending_removal(channel_id: int, message_id: int, user_id: int, emoji_str: str) -> None:
    _pending_bot_removals.add((channel_id, message_id, user_id, emoji_str))


def consume_pending_removal(channel_id: int, message_id: int, user_id: int, emoji_str: str) -> bool:
    """return True if the (channel_id, message_id, user_id, emoji_str) key was present.
    consumes the key on hit so a single registration cannot suppress two events."""
    key = (channel_id, message_id, user_id, emoji_str)
    if key in _pending_bot_removals:
        _pending_bot_removals.discard(key)
        return True
    return False


def discard_pending_removal(channel_id: int, message_id: int, user_id: int, emoji_str: str) -> None:
    """drop a key without claiming it; for use when the discord.remove_reaction call fails
    and we still want one-vote enforcement to proceed without leaving stale entries"""
    _pending_bot_removals.discard((channel_id, message_id, user_id, emoji_str))
