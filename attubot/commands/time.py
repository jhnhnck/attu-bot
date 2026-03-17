"""
AttuBot - Administrative Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import ApplicationContext, Bot, Permissions, SlashCommandGroup

from attubot import config
from attubot.client.calendar import get_year_status, move_epoch
from attubot.client.years import Year
from attubot.logging import get_logger
from attubot.tasks import nova_year_task, scheduler


logger = get_logger(__name__)

# --- Time Commands ---

time_group = SlashCommandGroup('time', default_member_permissions=Permissions.all(), description='Modify various options controlling the passage of time (Admin only)')


@time_group.command(name='advance', description='Manually advance to the next year, ignoring all checks')
async def time_advance(ctx: ApplicationContext):
    latest_year = await Year.get_latest(ctx.guild.id)
    forced_year = (latest_year.year if latest_year else 0) + 1
    _, year = get_year_status(ctx.guild.id)
    cfg = config.guild(ctx.guild.id)

    logger.info(f'weap. year forced by admin: expected={year} doing={forced_year}')
    await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
    scheduler.add_job(
        nova_year_task._advance_year(cfg, forced_year),
        f'ManualYearAdvance[{cfg.guild.id}]',
    )


@time_group.command(name='pause', description='Pause the passage of time')
async def time_pause(ctx: ApplicationContext):
    await ctx.respond('the passage of time has been stopped')
    await config.guild(ctx.guild.id).pause_time()


@time_group.command(name='resume', description='Resume the passage of time')
async def time_resume(ctx: ApplicationContext):
    guild = config.guild(ctx.guild.id)
    await move_epoch(guild.epoch.length, guild=ctx.guild.id)

    await ctx.respond(f'the passage of time has been resumed; epoch at **{guild.epoch.year} PC** (<t:{guild.epoch.time}:f>)')
    await guild.resume_time()


@time_group.command(name='dilate', description='Adjust the rate at which time progresses')
@discord.commands.option(name='days', required=True, description='Dilation amount (in days)', input_type=int)
async def time_dilate(ctx: ApplicationContext, days):
    guild = config.guild(ctx.guild.id)

    # catch to keep from trying entering number of weeks
    if days > 0 and days % 7 != 0:
        await ctx.respond('Failed: dilation amount must be divisible by 7', ephemeral=True)
        return

    if guild.epoch.paused:
        await guild.set_year_length(days)
        await ctx.respond(f'time set to **{guild.epoch.length} days per year**')

    else:
        await move_epoch(days, guild=ctx.guild.id)
        await ctx.respond(f'time set to **{guild.epoch.length} days per year**; epoch at **{guild.epoch.year} PC** (<t:{guild.epoch.time}:f>)')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(time_group)
