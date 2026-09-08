# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.remind | reminder slash commands."""

import time
import uuid
from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext, Bot, SlashCommandGroup
from discord.ext import commands

from nova_core.client.core import config
from nova_core.client.embeds import make_embed
from nova_core.client.util import is_authorized_guild
from nova_core.reminders.documents import ReminderDocument
from nova_core.reminders.task import _get_repo, compute_fire_time, format_attu_date, reminder_task


logger = structlog.stdlib.get_logger(__name__)

remind_group = SlashCommandGroup('remind', description='reminders for in-universe Haracalnde dates')


# --- /remind add ---


@remind_group.command(name='add', description='set a reminder for a Haracalnde date')
@discord.commands.option(name='year', required=True, description='which Haracalnde year to fire in (PC)', input_type=int, min_value=1)
@discord.commands.option(name='month', required=False, description='which month to fire in (1-12)', input_type=int, min_value=1, max_value=12)
@discord.commands.option(name='day', required=False, description='when in the month to fire (1-30)', input_type=int, min_value=1, max_value=30)
@discord.commands.option(name='note', required=False, description='note to include with the reminder (optional)', input_type=str)
@commands.check(is_authorized_guild)
async def remind_add(ctx: ApplicationContext, year: int, month: int | None = None, day: int | None = None, note: str | None = None):
    if day is not None and month is None:
        await ctx.respond('day needs a month to go with it', ephemeral=True)
        return

    guild_config = config.guild(ctx.guild.id)

    if guild_config.epoch.paused:
        await ctx.respond('time is paused', ephemeral=True)
        return

    reminder = ReminderDocument(
        reminder_id=str(uuid.uuid4()),
        guild_id=ctx.guild.id,
        user_id=ctx.user.id,
        channel_id=ctx.channel.id,
        attu_year=year,
        attu_month=month,
        attu_day=day,
        note=note or '',
        created_at=int(time.time()),
    )

    fire_dt = await compute_fire_time(reminder)
    if fire_dt is None:
        await ctx.respond("I couldn't work out when that date lands", ephemeral=True)
        return

    from datetime import datetime

    if fire_dt <= datetime.now().astimezone():
        await ctx.respond('that date has already passed', ephemeral=True)
        return

    repo = _get_repo()
    await repo.insert(reminder)
    reminder_task.request_wake()

    date_str = format_attu_date(reminder)
    fire_ts = int(fire_dt.timestamp())
    description = f'{date_str}\n> {reminder.note}' if reminder.note else date_str
    embed = make_embed(title='Reminder', description=description)
    embed.add_field(name='date', value=f'<t:{fire_ts}:R>', inline=False)
    await ctx.respond(embed=embed)

    # grab the bot response message id for jump URL construction
    try:
        response_msg = await ctx.interaction.original_response()
        await repo.update_message_id(reminder.reminder_id, response_msg.id)
    except discord.HTTPException:
        pass  # non-critical; delivery will just omit the jump URL


# --- /remind list ---


@remind_group.command(name='list', description='show your active reminders')
@commands.check(is_authorized_guild)
async def remind_list(ctx: ApplicationContext):
    repo = _get_repo()
    reminders = await repo.list_active_for_user(ctx.guild.id, ctx.user.id)

    if not reminders:
        await ctx.respond('you have no active reminders')
        return

    lines = []
    for r in reminders:
        date_str = format_attu_date(r)
        fire_dt = await compute_fire_time(r)
        fire_str = f'<t:{int(fire_dt.timestamp())}:R>' if fire_dt else 'unknown'
        note_str = f' - {r.note}' if r.note else ''
        short_id = r.reminder_id[:8]
        lines.append(f'`{short_id}` **{date_str}** {fire_str}{note_str}')

    embed = make_embed(title='Your Reminders', description='\n'.join(lines))
    await ctx.respond(embed=embed)


# --- /remind cancel ---


@remind_group.command(name='cancel', description='cancel an active reminder')
@discord.commands.option(name='reminder_id', required=True, description='which reminder to cancel (from /remind list)', input_type=str)
@commands.check(is_authorized_guild)
async def remind_cancel(ctx: ApplicationContext, reminder_id: str):
    repo = _get_repo()
    reminder_id = reminder_id.strip()

    # try full uuid first, then prefix match
    reminder = await repo.get(reminder_id)
    if reminder is None:
        reminder = await repo.get_by_prefix(reminder_id, ctx.guild.id, ctx.user.id)

    if reminder is None or reminder.guild_id != ctx.guild.id:
        await ctx.respond('no reminder with that id', ephemeral=True)
        return

    if reminder.user_id != ctx.user.id:
        await ctx.respond("that reminder isn't yours", ephemeral=True)
        return

    if reminder.fired:
        await ctx.respond('you have already been reminded of that', ephemeral=True)
        return

    date_str = format_attu_date(reminder)
    await repo.delete(reminder.reminder_id)
    await ctx.respond(f'reminder for **{date_str}** cancelled')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(cast('ApplicationCommand', remind_group))
