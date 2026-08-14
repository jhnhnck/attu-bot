# SPDX-License-Identifier: Apache-2.0
"""nova_core.starboard | starboard feature manifest."""

import asyncio

import structlog

from nova_core.config import GuildStarboard
from nova_core.manifest import FeatureManifest
from nova_core.starboard.documents import StarredMessageDocument
from nova_core.starboard.repositories import StarboardRepository


logger = structlog.stdlib.get_logger(__name__)

# background tasks (index init) held here to prevent garbage collection before completion
_bg_tasks: set = set()


async def _init_indexes(starboard_repo: StarboardRepository) -> None:
    """init starboard repo indexes; errors are logged, not raised - mirrors _try_init_indexes pattern."""
    try:
        await asyncio.wait_for(starboard_repo.init_indexes(), timeout=90.0)
        logger.debug('starboard indexes ready')
    except TimeoutError:
        logger.warning('starboard index init timed out after 90s (indexes may still be building in db)')
    except Exception as e:
        logger.warning(f'starboard index init failed (indexes may still be building): {e!s}')


def init_repos(db) -> None:
    """wire starboard repository singleton; called by FeatureContext._wire_documents() with MongoStorage.

    db.get_db() is called here rather than passing db directly because the loader
    passes MongoStorage (the connection manager), not the AsyncDatabase handle.
    """
    from nova_core.starboard import handlers as _handlers

    database = db.get_db()
    _handlers._starboard_repo = StarboardRepository(database)
    # schedule async index init without blocking the synchronous call site;
    # store reference in _bg_tasks to prevent the task from being gc'd before it finishes
    _task = asyncio.ensure_future(_init_indexes(_handlers._starboard_repo))
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)


def _starboard_enabled(guild_id: int) -> bool:
    """return True when the starboard is enabled for this guild; fails open so a
    config error never silently suppresses the starboard"""
    from nova_core.client.core import config

    try:
        return config.guild(guild_id).starboard.enabled
    except Exception:
        return True


# --- Manifest event handlers ---
# registered via bot.add_listener() by FeatureContext._wire_event_handlers().
# guild_id guard is required; handlers also check sb.channel_id and sb.emojis internally.


async def _on_raw_reaction_add(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.client.core import config
    from nova_core.starboard import handlers

    if payload.guild_id not in config.valid_guilds:
        return
    if _starboard_enabled(payload.guild_id):
        await handlers.handle_star_add(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            user_id=payload.user_id,
            emoji_str=str(payload.emoji),
            is_burst=payload.burst,
        )


async def _on_raw_reaction_remove(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.client.core import config
    from nova_core.starboard import handlers

    if payload.guild_id not in config.valid_guilds:
        return
    if _starboard_enabled(payload.guild_id):
        await handlers.handle_star_remove(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            user_id=payload.user_id,
            emoji_str=str(payload.emoji),
            is_burst=payload.burst,
        )


async def _on_raw_reaction_clear(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.client.core import config
    from nova_core.starboard import handlers

    if payload.guild_id not in config.valid_guilds:
        return
    if _starboard_enabled(payload.guild_id):
        await handlers.handle_star_clear(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            message_id=payload.message_id,
        )


async def _on_raw_reaction_clear_emoji(payload) -> None:
    if payload.guild_id is None:
        return
    from nova_core.client.core import config
    from nova_core.starboard import handlers

    if payload.guild_id not in config.valid_guilds:
        return
    if _starboard_enabled(payload.guild_id):
        await handlers.handle_star_clear_emoji(
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            message_id=payload.message_id,
            emoji_str=str(payload.emoji),
        )


def _setup_commands(bot) -> None:
    """register starboard slash commands; deferred import to avoid circular dependency."""
    from nova_core.commands.stars import setup as _setup

    _setup(bot)


manifest = FeatureManifest(
    name='starboard',
    event_handlers={
        'on_raw_reaction_add': _on_raw_reaction_add,
        'on_raw_reaction_remove': _on_raw_reaction_remove,
        'on_raw_reaction_clear': _on_raw_reaction_clear,
        'on_raw_reaction_clear_emoji': _on_raw_reaction_clear_emoji,
    },
    setup=_setup_commands,
    guild_config_key='starboard',
    guild_config_model=GuildStarboard,
    document_classes=[StarredMessageDocument],
    repository_classes=[StarboardRepository],
)
