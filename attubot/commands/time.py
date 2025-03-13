"""
AttuBot - Administrative Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""  # noqa: A005

import discord
from discord import Permissions

from attubot.config import Config
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import get_year_status, move_epoch

logger = get_logger(__name__)

# --- Time Commands ---

time_group = discord.SlashCommandGroup('time', default_member_permissions=Permissions.all(), description='Modify various options controlling the passage of time (Admin only)')

@time_group.command(name='advance', guilds_only=True, description='Manually advance to the next year, ignoring all checks')
async def time_advance(ctx):
    forced_year = (await YearMarker.total()) + 1
    _, year = get_year_status()
    cog = ctx.bot.get_cog('NewYearEvent')

    logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
    await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
    await cog.advance_year(forced_year)

@time_group.command(name='pause', guilds_only=True, description='Pause the passage of time')
async def time_pause(ctx):
    await ctx.respond('The passage of time has been stopped')
    Config.pause_time()

@time_group.command(name='resume', guilds_only=True, description='Resume the passage of time')
async def time_resume(ctx):
    await move_epoch(Config.epoch_length)

    await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')
    Config.resume_time()

@time_group.command(name='dilate', guilds_only=True, description='Adjust the rate at which time progresses')
@discord.commands.option(name='days', required=True, description='Dilation amount (in days)', input_type=int)
async def time_dilate(ctx, days):
    # catch to keep from trying entering number of weeks
    if days > 0 and days % 7 != 0:
        await ctx.respond('Failed: Dilation amount must be divisible by 7', ephemeral=True)
        return

    if Config.time_paused:
        Config.set_epoch_length(days)
        await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year**')

    else:
        await move_epoch(days)
        await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year** with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(time_group)

