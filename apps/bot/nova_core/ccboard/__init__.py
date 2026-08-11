# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard | reaction-board feature manifest."""

import asyncio

import structlog

from nova_core.ccboard.documents import BoardEntryDocument, ReactionDocument
from nova_core.ccboard.repositories import EntryRepository, ReactionRepository
from nova_core.config import GuildCCBoard
from nova_core.manifest import FeatureManifest


logger = structlog.stdlib.get_logger(__name__)

# background tasks (index init) held here to prevent garbage collection before completion
_bg_tasks: set = set()

# repository singletons populated by init_repos() at startup.
# the watcher and manager read these at call time; importing them at module scope
# would race with init_repos().
_reaction_repo: ReactionRepository | None = None
_entry_repo: EntryRepository | None = None


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
# key shape: (channel_id, message_id, user_id, emoji_str) -- these are the values from
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


async def _init_indexes(reaction_repo: ReactionRepository, entry_repo: EntryRepository) -> None:
    """init ccboard repo indexes; errors are logged, not raised - mirrors _try_init_indexes pattern."""
    for repo, label in ((reaction_repo, 'ccboard_reactions'), (entry_repo, 'ccboard_entries')):
        try:
            await asyncio.wait_for(repo.init_indexes(), timeout=90.0)
            logger.debug(f'{label} indexes ready')
        except TimeoutError:
            logger.warning(f'{label} index init timed out after 90s (indexes may still be building in db)')
        except Exception as e:
            logger.warning(f'{label} index init failed (indexes may still be building): {e!s}')


def init_repos(db) -> None:
    """wire ccboard repository singletons; called by FeatureContext._wire_documents() with MongoStorage.

    db.get_db() is called here rather than passing db directly because the loader
    passes MongoStorage (the connection manager), not the AsyncDatabase handle.
    """
    import nova_core.ccboard as _self

    database = db.get_db()
    _self._reaction_repo = ReactionRepository(database)
    _self._entry_repo = EntryRepository(database)
    # schedule async index init without blocking the synchronous call site;
    # store reference in _bg_tasks to prevent the task from being gc'd before it finishes
    _task = asyncio.ensure_future(_init_indexes(_self._reaction_repo, _self._entry_repo))
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)


# --- Manifest event handlers ---
# these are registered via bot.add_listener() by FeatureContext._wire_event_handlers().
# guild_id guard is required; the watcher functions also check cfg.enabled internally.


async def _on_raw_reaction_add(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.ccboard import watcher as ccboard_watcher
    from nova_core.client.core import bot

    # payload.member is the reactor for raw_reaction_add; if missing or partial,
    # fall back to a guild member lookup so bot-authored reactions are filtered
    is_bot = False
    member = payload.member
    if member is not None:
        is_bot = bool(getattr(member, 'bot', False))
    else:
        try:
            fetched = await bot.get_or_fetch_member(bot.get_guild(payload.guild_id), payload.user_id)
            if fetched is not None:
                is_bot = bool(getattr(fetched, 'bot', False))
        except Exception:
            # leave is_bot False so a missing member lookup doesn't silently drop reactions
            is_bot = False

    await ccboard_watcher.handle_reaction_add(
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
        emoji_str=str(payload.emoji),
        is_burst=payload.burst,
        is_bot=is_bot,
    )


async def _on_raw_reaction_remove(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.ccboard import watcher as ccboard_watcher

    await ccboard_watcher.handle_reaction_remove(
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        user_id=payload.user_id,
        emoji_str=str(payload.emoji),
    )


async def _on_raw_reaction_clear(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.ccboard import watcher as ccboard_watcher

    await ccboard_watcher.handle_reaction_clear(
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
    )


async def _on_raw_reaction_clear_emoji(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.ccboard import watcher as ccboard_watcher

    await ccboard_watcher.handle_reaction_clear_emoji(
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        message_id=payload.message_id,
        emoji_str=str(payload.emoji),
    )


def _setup_commands(bot) -> None:
    """register ccboard slash commands; deferred import to avoid circular dependency."""
    from nova_core.commands.cc_stars import setup as _setup

    _setup(bot)


# import task singletons AFTER all module-level state is defined so that auditor.py and
# manager.py can safely do `from nova_core import ccboard` at their module top level and
# receive a partial-but-usable module (all utilities are already defined above).
from nova_core.ccboard.auditor import auditor_task  # noqa: E402
from nova_core.ccboard.manager import manager_task  # noqa: E402


manifest = FeatureManifest(
    name='ccboard',
    tasks=[manager_task, auditor_task],
    event_handlers={
        'on_raw_reaction_add': _on_raw_reaction_add,
        'on_raw_reaction_remove': _on_raw_reaction_remove,
        'on_raw_reaction_clear': _on_raw_reaction_clear,
        'on_raw_reaction_clear_emoji': _on_raw_reaction_clear_emoji,
    },
    setup=_setup_commands,
    guild_config_key='ccboard',
    guild_config_model=GuildCCBoard,
    document_classes=[ReactionDocument, BoardEntryDocument],
    repository_classes=[ReactionRepository, EntryRepository],
)
