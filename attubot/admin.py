"""
AttuBot - Administrative and Debug Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import datetime
from os import getenv

import discord
from discord import Permissions
from discord.ext import commands

from attubot import __version__
from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import get_year_span, get_year_status, move_epoch
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Permissions Check ---

def is_bot_owner(ctx):
    return ctx.user.id == Config.bot_owner

# --- Admin Command ---

time = discord.SlashCommandGroup('time',
                                 default_member_permissions=Permissions.all(),
                                 description='Modify various options controlling the passage of time (Admin only)')

@time.command(guilds_only=True, description='Manually advance to the next year, ignoring all checks')
@commands.check(is_bot_owner)
async def advance(ctx):
    forced_year = len(Config.timestamps) + 1
    _, year = get_year_status()
    cog = ctx.bot.get_cog('NewYearEvent')

    logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
    await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
    await cog.advance_year(forced_year)

@time.command(guilds_only=True, description='Pause the passage of time')
@commands.check(is_bot_owner)
async def pause(ctx):
    await ctx.respond('The passage of time has been stopped')
    Config.pause_time()

@time.command(guilds_only=True, description='Resume the passage of time')
@commands.check(is_bot_owner)
async def resume(ctx):
    move_epoch(Config.epoch_length)

    await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')
    Config.resume_time()

@time.command(guilds_only=True, description='Adjust the rate at which time progresses')
@commands.check(is_bot_owner)
@discord.commands.option(name='days', required=True, description='Dilation amount (in days)', input_type=int)
async def dilate(ctx, days):
    # catch to keep from trying entering number of weeks
    if days > 0 and days % 7 != 0:
        await ctx.respond('Failed: Dilation amount must be divisible by 7', ephemeral=True)
        return

    if Config.time_paused:
        Config.set_epoch_length(days)
        await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year**')

    else:
        move_epoch(days)
        await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year** with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')

# --- Debug Command ---

debug = discord.SlashCommandGroup('debug',
                                   default_member_permissions=Permissions.all(),
                                   description='Check the version, retrieve year statistics or force an error (Admin only)')

@debug.command(guilds_only=True, description='Displays the current version and container build time')
async def version(ctx):
    build_format = '%a %b %d %H:%M:%S %Z %Y'
    build_time = datetime.strptime(getenv('BUILD_TIME'), build_format)

    await ctx.respond('\n'.join([
        f'Version: {__version__}',
        f'Container Build Time: <t:{int(build_time.timestamp())}:f>',
    ]))

@debug.command(guilds_only=True, description='Returns the current state of time tracking calculations')
async def year_stats(ctx):
    elapsed_days, current_year = get_year_status()
    year_span = get_year_span(current_year)
    cog = ctx.bot.get_cog('NewYearEvent')

    await ctx.respond('\n'.join([
        f'Current Year: {current_year} PC',
        f'Year Span: <t:{year_span.start_time}:f> to <t:{year_span.end_time}:f> ({year_span.duration} days)',
        f'Attu Epoch: {Config.epoch_year} PC at <t:{Config.epoch_time}:f>',
        f'Time Since Epoch: {elapsed_days} Days',
        f'Next Task Iteration: <t:{int(cog.task_year_check.next_iteration.timestamp())}:f>',
    ]))

@debug.command(guilds_only=True, description='Causes an internal error to be thrown')
@commands.check(is_bot_owner)
async def force_error(ctx):
    await ctx.respond('Forcing an error message')
    math = 10 / 0  # noqa: F841

# --- Wiki Commands ---

@discord.slash_command(guilds_only=True, default_member_permissions=Permissions.all(),
                       description='Blocks a specified user from the wiki (Admin only)')
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
async def wiki_block(ctx, user, reason):
    # check if link to the user
    extract = re.search(r'User:(.*)$', user)

    if extract is not None:
        user = extract[1]

    await ctx.respond(f'Blocking user "{user}": {reason}')

    wiki = AttuWiki()
    wiki.authenticate(Config.wiki_user, Config.wiki_key)
    wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(time)
    bot.add_application_command(debug)
    bot.add_application_command(wiki_block)
