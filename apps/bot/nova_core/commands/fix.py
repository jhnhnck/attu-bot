# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.fix | background job functions for repair and maintenance operations.

discord slash commands have been removed; these jobs are invoked via the bridge ops
endpoints or used internally by other subsystems.
"""

from datetime import timedelta

import discord
import structlog
from discord import Bot

from nova_core.client.core import bot, config
from nova_core.tasks.message_backfill import MessageBackfillTask


logger = structlog.stdlib.get_logger(__name__)


async def _safe_edit(status_msg: discord.Message | None, content: str) -> discord.Message | None:
    """edit the status message safely; returns None if the edit fails so callers can stop retrying."""
    if status_msg is None:
        return None
    try:
        await status_msg.edit(content=content)
        return status_msg
    except discord.HTTPException as err:
        logger.warning(f'fix: status message edit failed ({err}), further updates disabled')
        return None


async def job_backfill_channel(
    channel_id: int,
    guild_id: int,
    status_msg: discord.Message | None = None,
    *,
    reconcile_recent: bool = False,
    reconcile_lookback: timedelta | None = None,
    task: MessageBackfillTask | None = None,
):
    """scan a channel and backfill any messages not already stored."""
    channel = bot.get_channel(channel_id)

    if channel is None:
        logger.error(f'fix messages: channel {channel_id} not found in cache')
        await _safe_edit(status_msg, f'Error: channel {channel_id} not found')
        return 0, 0

    backfill_task = task or MessageBackfillTask()
    backfilled = 0
    reconciled = 0

    try:
        backfilled = await backfill_task._backfill_channel(guild_id, channel)  # pyright: ignore[reportArgumentType]
    except Exception as err:
        logger.error(f'fix messages: error scanning channel {channel_id}: {err}')
        await _safe_edit(status_msg, f'Error scanning <#{channel_id}>; check logs')
        return 0, 0

    if reconcile_recent:
        try:
            reconciled = await backfill_task._reconcile_recent_channel(guild_id, channel, lookback=reconcile_lookback)  # pyright: ignore[reportArgumentType]
        except Exception as err:
            logger.warning(f'fix messages: recent reconcile failed for {channel_id}: {err}')

    summary = f'Done! Backfilled {backfilled:,} messages in <#{channel_id}>'
    if reconcile_recent:
        summary += f', reconciled {reconciled:,} recent entries'

    await _safe_edit(status_msg, summary)

    return backfilled or 0, reconciled or 0


async def job_reconcile_guild(guild_id: int, status_msg: discord.Message | None = None, *, lookback: timedelta | None = None):
    """run a full reconciliation pass across all readable channels and threads."""
    task = MessageBackfillTask()

    guild_obj = bot.get_guild(guild_id)
    if guild_obj is None:
        logger.error(f'fix reconcile: guild {guild_id} not in cache')
        await _safe_edit(status_msg, 'Guild not in cache')
        return

    me = guild_obj.me
    if me is None:
        await _safe_edit(status_msg, 'Bot member not ready')
        return

    try:
        guild_config = config.guild(guild_id)
    except Exception as err:
        await _safe_edit(status_msg, f'Error: {err}')
        return

    try:
        channels = await task._collect_channels(guild_obj, guild_config.channels.logs, me)
    except Exception as err:
        await _safe_edit(status_msg, f'Unable to collect channels: {err}')
        return

    total_backfilled = 0
    total_reconciled = 0

    for channel in channels:
        status_msg = await _safe_edit(status_msg, f'Scanning <#{channel.id}>...')
        backfilled, reconciled = await job_backfill_channel(
            channel.id,
            guild_id,
            status_msg=status_msg,
            reconcile_recent=True,
            reconcile_lookback=lookback,
            task=task,
        )
        total_backfilled += backfilled or 0
        total_reconciled += reconciled or 0

    summary = f'Reconcile complete: {total_backfilled} backfilled, {total_reconciled} reconciled'
    logger.info(f'fix reconcile: {summary} (guild {guild_id})')
    await _safe_edit(status_msg, summary)


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')
