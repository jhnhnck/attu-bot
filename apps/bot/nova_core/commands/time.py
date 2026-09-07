# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.time | administrative commands."""

import discord
import structlog
from discord import ApplicationContext, Bot, Permissions, SlashCommandGroup

from nova_core.client.calendar import get_year_status, move_epoch
from nova_core.client.core import config
from nova_core.client.years import Year
from nova_core.tasks import nova_year_task, scheduler


logger = structlog.stdlib.get_logger(__name__)

# --- Time Commands ---

time_group = SlashCommandGroup('time', default_member_permissions=Permissions.all(), description='control the passage of time (admin only)')


@time_group.command(name='advance', description='advance to the next year, ignoring all checks')
async def time_advance(ctx: ApplicationContext):
    latest_year = await Year.get_latest(ctx.guild.id)
    forced_year = (latest_year.year if latest_year else 0) + 1
    _, year = get_year_status(ctx.guild.id)
    cfg = config.guild(ctx.guild.id)

    logger.info(f'weap. year forced by admin: expected={year} doing={forced_year}')
    await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
    scheduler.add_job(nova_year_task._advance_year(cfg, forced_year), 'ManualYearAdvance', cfg.guild.id)


@time_group.command(name='pause', description='pause the passage of time')
async def time_pause(ctx: ApplicationContext):
    await ctx.respond('the passage of time has been stopped')
    await config.guild(ctx.guild.id).pause_time()


@time_group.command(name='resume', description='resume the passage of time')
async def time_resume(ctx: ApplicationContext):
    guild = config.guild(ctx.guild.id)
    await move_epoch(guild.epoch.length, guild=ctx.guild.id)

    await ctx.respond(f'the passage of time has been resumed; epoch at **{guild.epoch.year} PC** (<t:{guild.epoch.time}:f>)')
    await guild.resume_time()


@time_group.command(name='dilate', description='change how many days a year takes')
@discord.commands.option(name='days', required=True, description='how many days a year should take', input_type=int)
async def time_dilate(ctx: ApplicationContext, days):
    guild = config.guild(ctx.guild.id)

    # catch to keep from trying entering number of weeks
    if days > 0 and days % 7 != 0:
        await ctx.respond('dilation has to be a multiple of 7 days', ephemeral=True)
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
