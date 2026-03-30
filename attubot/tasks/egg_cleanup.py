"""
AttuBot - Egg Thread Cleanup Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime, timedelta

import discord

from attubot import bot, config
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class EggCleanupTask(BaseTask):
    """Periodic task that deletes non-egg messages from egg threads.

    Runs every 6 hours during egg season. For each user's egg thread, deletes
    any message older than 12 hours whose id is not tracked in the egg database.
    """

    name: str = 'EggCleanupTask'
    interval: timedelta | None = timedelta(hours=6)
    run_immediately: bool = False

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        guild_cfg = config.primary()
        guild = bot.get_guild(guild_cfg.id)
        if guild is None:
            logger.warn('egg cleanup: primary guild not in cache')
            return

        # local imports to avoid circular deps with tasks/__init__.py
        from attubot.eggs.hatching import _egg_repo, _egg_user_repo

        cutoff = datetime.now(tz=UTC) - timedelta(hours=12)
        user_docs = await _egg_user_repo.list_all(guild_cfg.id)
        total_deleted = 0

        for user_doc in user_docs:
            if not user_doc.thread_id:
                continue

            thread = bot.get_channel(user_doc.thread_id)
            if thread is None:
                try:
                    thread = await guild.fetch_channel(user_doc.thread_id)
                except discord.NotFound:
                    continue

            # build set of known egg message ids for this user
            unhatched = await _egg_repo.list_unhatched(guild_cfg.id, user_doc.user_id)
            hatched = await _egg_repo.list_hatched(guild_cfg.id, user_doc.user_id)
            egg_message_ids: set[int] = {e.message_id for e in unhatched + hatched if e.message_id is not None}

            # oldest-first; break once we reach messages newer than the cutoff
            async for message in thread.history(oldest_first=True, limit=None):  # type: ignore[union-attr]
                if message.created_at.replace(tzinfo=UTC) >= cutoff:
                    break
                if message.id in egg_message_ids:
                    continue
                if message.reactions:
                    logger.debug(f'egg cleanup: skipping message {message.id} (has reactions)')
                    continue
                try:
                    await message.delete()
                    total_deleted += 1
                except (discord.NotFound, discord.Forbidden):
                    pass  # already gone or no permission; continue

        logger.info(f'egg cleanup: deleted {total_deleted} non-egg message(s)')


# singleton instance for registration
egg_cleanup_task = EggCleanupTask()
