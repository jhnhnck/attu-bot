"""
AttuBot - Reminder Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime, timedelta

import discord

from attubot import bot, config
from attubot.client.calendar import get_year_span
from attubot.client.util import format_message_link, webhook_logging
from attubot.config import UnauthorizedGuild
from attubot.database.models import ReminderDocument
from attubot.database.repositories import ReminderRepository
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)

# module-level repo singleton; wired by database/__init__.py
_reminder_repo: ReminderRepository | None = None


def _get_repo() -> ReminderRepository:
    if _reminder_repo is None:
        raise RuntimeError('reminder repo not initialized')
    return _reminder_repo


# --- Helpers ---


def format_attu_date(reminder: ReminderDocument) -> str:
    """Format a reminder's target date as a human-readable haracalnde date string."""
    if reminder.attu_month is None:
        return f'Year {reminder.attu_year} PC'
    if reminder.attu_day is None:
        return f'month {reminder.attu_month}, Year {reminder.attu_year} PC'
    return f'{reminder.attu_day}-{reminder.attu_month} {reminder.attu_year} PC'


async def compute_fire_time(reminder: ReminderDocument) -> datetime | None:
    """Convert a reminder's haracalnde date to a real-world datetime.

    Returns None if the fire time cannot be computed (paused or unauthorized guild).
    """
    try:
        cfg = config.guild(reminder.guild_id)
    except UnauthorizedGuild:
        return None

    if cfg.epoch.paused:
        return None

    span = await get_year_span(reminder.attu_year, reminder.guild_id)
    if span.start_time <= 0 or span.end_time <= 0:
        return None

    if reminder.attu_month is None:
        # year-only: fire at start of the year (rollover)
        return datetime.fromtimestamp(span.start_time).astimezone()

    # compute haracalnde position within the year [0, 359]
    month = reminder.attu_month
    day = reminder.attu_day if reminder.attu_day is not None else 1
    haracalnde_pos = (month - 1) * 30 + (day - 1)

    # linear interpolation within the year span
    span_seconds = span.end_time - span.start_time
    fire_ts = span.start_time + (haracalnde_pos / 360) * span_seconds
    return datetime.fromtimestamp(fire_ts).astimezone()


async def _deliver_reminder(reminder: ReminderDocument) -> None:
    """Send the reminder notification in the original channel, falling back to meta_chat."""
    guild = bot.get_guild(reminder.guild_id)
    if guild is None:
        logger.warn(f'reminder {reminder.reminder_id}: guild {reminder.guild_id} not found')
        return

    channel = guild.get_channel_or_thread(reminder.channel_id)

    if channel is None:
        try:
            cfg = config.guild(reminder.guild_id)
            meta_id = cfg.channels.meta_chat
            if meta_id:
                channel = guild.get_channel_or_thread(meta_id)
        except UnauthorizedGuild:
            pass

    if channel is None:
        logger.warn(f'reminder {reminder.reminder_id}: no valid channel found for delivery')
        return

    date_str = format_attu_date(reminder)
    note_str = f'\n> {reminder.note}' if reminder.note else ''

    if reminder.message_id:
        jump_url = format_message_link(reminder.guild_id, reminder.channel_id, reminder.message_id)
        origin_str = f'\n{jump_url}'
    else:
        origin_str = ''

    msg = f'<@{reminder.user_id}> reminder: **{date_str}** has arrived!{note_str}{origin_str}'

    try:
        await channel.send(msg)
    except discord.HTTPException as e:
        logger.error(f'reminder {reminder.reminder_id}: failed to send: {e!s}')


# --- Task ---


class ReminderTask(BaseTask):
    """Wakes up at the exact time of the next pending reminder and delivers it.

    Uses dynamic scheduling via next_run() - sleeps until the earliest fire time
    across all unfired reminders rather than polling on a fixed interval.
    """

    name: str = 'ReminderCheck'
    interval = None

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()

    async def next_run(self) -> datetime | None:
        """Return the earliest real-world fire time across all unfired reminders."""
        repo = _get_repo()
        reminders = await repo.list_all_unfired()

        if not reminders:
            return datetime.now().astimezone() + timedelta(minutes=30)

        earliest: datetime | None = None
        now = datetime.now().astimezone()

        for reminder in reminders:
            fire_dt = await compute_fire_time(reminder)
            if fire_dt is None:
                continue

            # overdue — fire ASAP
            if fire_dt <= now:
                return now

            if earliest is None or fire_dt < earliest:
                earliest = fire_dt

        if earliest is None:
            # all reminders belong to paused/unauthorized guilds
            return datetime.now().astimezone() + timedelta(minutes=30)

        return earliest

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Fire any overdue reminders."""
        repo = _get_repo()
        reminders = await repo.list_all_unfired()
        now_ts = int(datetime.now().astimezone().timestamp())

        for reminder in reminders:
            fire_dt = await compute_fire_time(reminder)
            if fire_dt is None:
                continue
            if fire_dt.timestamp() <= now_ts:
                await _deliver_reminder(reminder)
                await repo.mark_fired(reminder.reminder_id, now_ts)
                logger.info(f'fired reminder {reminder.reminder_id} for user {reminder.user_id}')


# singleton instance for registration
reminder_task = ReminderTask()
