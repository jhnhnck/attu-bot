"""
AttuBot - Administrative and Debug Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime
from os import getenv

import discord
from discord import Permissions
from discord.ext import commands
from discord.utils import snowflake_time

from attubot import __version__
from attubot.config import Config
from attubot.logging import get_logger
from attubot.markers import YearMarker, markers_count
from attubot.util import format_message_link, get_year_span, get_year_status, is_authorized_guild, is_bot_owner, move_epoch

logger = get_logger(__name__)

# --- Admin Commands ---

time_group = discord.SlashCommandGroup('time', default_member_permissions=Permissions.all(), description='Modify various options controlling the passage of time (Admin only)')

@time_group.command(name='advance', guilds_only=True, description='Manually advance to the next year, ignoring all checks')
@commands.check(is_bot_owner)
async def time_advance(ctx):
    forced_year = (await markers_count()) + 1
    _, year = get_year_status()
    cog = ctx.bot.get_cog('NewYearEvent')

    logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
    await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
    await cog.advance_year(forced_year)

@time_group.command(name='pause', guilds_only=True, description='Pause the passage of time')
@commands.check(is_bot_owner)
async def time_pause(ctx):
    await ctx.respond('The passage of time has been stopped')
    Config.pause_time()

@time_group.command(name='resume', guilds_only=True, description='Resume the passage of time')
@commands.check(is_bot_owner)
async def time_resume(ctx):
    await move_epoch(Config.epoch_length)

    await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')
    Config.resume_time()

@time_group.command(name='dilate', guilds_only=True, description='Adjust the rate at which time progresses')
@commands.check(is_bot_owner)
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

# --- Debug Commands ---

debug_group = discord.SlashCommandGroup('debug', default_member_permissions=Permissions.all(), description='Check the version, retrieve year statistics or force an error (Admin only)')

@debug_group.command(name='version', guilds_only=True, description='Displays the current version and container build time')
async def debug_version(ctx):
    build_format = '%a %b %d %H:%M:%S %Z %Y'
    build_time = datetime.strptime(getenv('BUILD_TIME'), build_format)

    await ctx.respond('\n'.join([
        f'Version: v{__version__}',
        f'Container Build Time: <t:{int(build_time.timestamp())}:f>',
    ]))

@debug_group.command(name='year_stats', guilds_only=True, description='Returns the current state of time tracking calculations')
async def debug_year_stats(ctx):
    elapsed_days, current_year = get_year_status()
    year_span = await get_year_span(current_year)
    cog = ctx.bot.get_cog('NewYearEvent')

    await ctx.respond('\n'.join([
        f'Current Year: {current_year} PC',
        f'Year Span: <t:{year_span.start_time}:f> to <t:{year_span.end_time}:f> ({year_span.duration} days)',
        f'Attu Epoch: {Config.epoch_year} PC at <t:{Config.epoch_time}:f>',
        f'Time Since Epoch: {elapsed_days} Days',
        f'Next Task Iteration: <t:{int(cog.task_year_check.next_iteration.timestamp())}:f>',
    ]))

@debug_group.command(name='force_error', guilds_only=True, description='Causes an internal error to be thrown')
@commands.check(is_bot_owner)
async def debug_force_error(ctx):
    await ctx.respond('Forcing an error message')
    math = 10 / 0  # noqa: F841

# --- Marker Commands ---

marker_group = discord.SlashCommandGroup('marker', description='Utlities related to managing year markers')

@marker_group.command(name='save', guilds_only=True, default_member_permissions=Permissions.all(), description='Updates marker to point to a different message (Admin only)')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='link', required=True, description='Message Link', input_type=str)
@discord.commands.option(name='force', required=False, description='Override Mode', input_type=bool, default=False)
@commands.check(is_authorized_guild)
async def marker_save(ctx, year: int, link: str, force: bool):
    _, current_year = get_year_status()

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    if 'discord.com/channels' not in link:
        await ctx.respond('Failed: Not a valid Discord message link', ephemeral=True)
        return

    # unpack url
    ids = link.split('/')[-3:]
    channel, message = int(ids[1]), int(ids[2])

    if channel not in Config.lore_channels and channel != Config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel', ephemeral=True)
        return

    # Check if close
    est_marker = await YearMarker.get(year=year, channel=0)
    time_diff = abs((snowflake_time(est_marker.message) - snowflake_time(message)).total_seconds())

    if time_diff > 600 and not force:
        await ctx.respond(f'Failed: Provided link is {int(time_diff)} seconds off from expected; if correct, override with `force:true`', ephemeral=True)
        return

    # Add or update marker
    marker, created = await YearMarker.get_or_create(year=year, channel=channel, defaults={'message': message})
    marker.message = message
    marker.exact = True
    await marker.save()

    verb = 'Created' if created else 'Updated'
    await ctx.respond(f'{verb} marker for Year {year} PC as {format_message_link(Config.attu_guild, marker.channel, marker.message)}')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(time_group)
    bot.add_application_command(debug_group)
    bot.add_application_command(marker_group)
