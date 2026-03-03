"""
AttuBot - Message Backfill Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta

import discord

from attubot import bot, config
from attubot.logging import get_logger
from attubot.messages import _get_repo, build_message_doc
from attubot.tasks.base import BaseTask

logger = get_logger(__name__)


class MessageBackfillTask(BaseTask):
    """One-shot task that runs at startup to backfill messages missed while the bot was offline.

    For each text channel in authorized guilds (excluding the logs channel), queries the
    latest stored message_id and fetches anything newer from the Discord API. Runs once
    immediately on start, then idles indefinitely.
    """

    name: str = 'MessageBackfillTask'
    interval: timedelta | None = None  # dynamic schedule - run once then idle
    run_immediately: bool = True

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()

    async def next_run(self):
        # after the initial run_immediately execution, return a far-future datetime to idle
        from datetime import datetime

        return datetime.now().astimezone() + timedelta(days=36500)

    async def _collect_channels(self, guild: discord.Guild, logs_channel_id: int, me: discord.Member) -> list[discord.TextChannel | discord.Thread]:
        """Return all readable text channels and active threads, excluding logs."""
        channels: list[discord.TextChannel | discord.Thread] = []

        for channel in guild.channels:
            if not isinstance(channel, discord.TextChannel):
                continue
            if channel.id == logs_channel_id:
                continue
            if not channel.permissions_for(me).read_message_history:
                continue
            channels.append(channel)

        # active threads are not included in guild.channels
        try:
            for thread in await guild.active_threads():
                if thread.parent_id == logs_channel_id:
                    continue
                if not thread.permissions_for(me).read_message_history:
                    continue
                channels.append(thread)
        except Exception as err:
            logger.warn(f'backfill: could not fetch active threads for guild {guild.id}: {err}')

        return channels

    async def run(self) -> None:
        """Backfill all text channels and active threads across all valid guilds."""
        total_new = 0
        total_channels = 0

        for guild_id in config.valid_guilds:
            guild = bot.get_guild(guild_id)
            if guild is None:
                logger.warn(f'backfill: guild {guild_id} not in cache, skipping')
                continue

            try:
                gc = config.guild(guild_id)
            except Exception as err:
                logger.debug(f'backfill: guild {guild_id} config unavailable: {err}')
                continue

            me = guild.me
            if me is None:
                continue

            channels = await self._collect_channels(guild, gc.channels.logs, me)

            for channel in channels:
                count = await self._backfill_channel(guild_id, channel)
                total_new += count
                total_channels += 1

        logger.info(f'backfill complete: {total_new} new messages stored across {total_channels} channels')

    async def _backfill_channel(self, guild_id: int, channel: discord.TextChannel | discord.Thread) -> int:
        """Fetch and store any messages newer than the last stored message_id in this channel.

        Returns the number of new messages stored.
        """
        repo = _get_repo()
        count = 0

        channel_label = f'#{channel.name} ({channel.id})'
        logger.info(f'backfill: scanning {channel_label}')

        try:
            latest_id = await repo.get_latest_in_channel(guild_id, channel.id)
        except Exception as err:
            logger.warn(f'backfill: could not query latest message for channel {channel.id}: {err}')
            return 0

        if latest_id is not None:
            logger.debug(f'backfill: resuming {channel_label} after message {latest_id}')
        else:
            logger.debug(f'backfill: no prior history for {channel_label}, fetching all')

        try:
            if latest_id is not None:
                # fetch only messages after the last known id
                after = discord.Object(id=latest_id)
                history = channel.history(after=after, oldest_first=True, limit=None)
            else:
                # no history at all - fetch everything
                history = channel.history(oldest_first=True, limit=None)

            async for message in history:
                try:
                    doc = await build_message_doc(message)
                    await repo.upsert(doc)
                    count += 1
                except Exception as err:
                    logger.warn(f'backfill: failed to store message {message.id} in channel {channel.id}: {err}')

        except discord.Forbidden:
            logger.debug(f'backfill: no permission to read history in {channel_label}')
        except Exception as err:
            logger.warn(f'backfill: error reading {channel_label}: {err}')

        if count > 0:
            logger.info(f'backfill: stored {count} new messages from {channel_label}')
        else:
            logger.debug(f'backfill: {channel_label} is up to date')

        return count


# singleton instance for registration
message_backfill_task = MessageBackfillTask()
