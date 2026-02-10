"""
AttuBot - User Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import datetime, timedelta
from typing import cast

import discord
from discord import ApplicationContext, Bot, SlashCommandGroup, TextChannel
from discord.enums import ChannelType
from discord.utils import snowflake_time

from attubot import config
from attubot.calendar import SECONDS_PER_DAY, get_year_span, get_year_status
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import format_message_link
from attubot.years import Year

logger = get_logger(__name__)

# --- Year Commands ---

year_group = SlashCommandGroup('year', description='Utilities related to current, past or future years')

@year_group.command(name='check', description='Prints out information related to a specified year; if not specified, year defaults to the next year')
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int, min_value=1)
async def year_check(ctx: ApplicationContext, year: int):
    guild_config = config.guild(ctx.guild.id)
    elapsed_days, current_year = get_year_status(guild=guild_config.id)
    year = year if year is not None else (current_year + 1)

    # invalid year input
    if year <= 0:
        await ctx.respond('Failed: Only years 1 PC or later are valid options', ephemeral=True)

    # prior years - read directly from Year records
    elif year < current_year:
        year_record = await Year.get(guild_config.id, year)
        if year_record:
            await ctx.respond(f'Year {year} PC lasted for {year_record.duration} days, starting on <t:{year_record.start_time}:d> and ending on <t:{year_record.end_time}:d>')
        else:
            # Fallback to computed span if no record exists
            year_span = await get_year_span(year, guild=guild_config.id)
            await ctx.respond(f'Year {year} PC lasted for {year_span.duration} days, starting on <t:{year_span.start_time}:d> and ending on <t:{year_span.end_time}:d>')

    # check if time is paused first
    elif guild_config.epoch.paused:
        await ctx.respond('Sorry! New Years is cancelled until further notice')

    # current year
    elif year == current_year:
        year_span = await get_year_span(year, guild=guild_config.id)
        await ctx.respond(f'Year {year} PC will last for {year_span.duration} days, which started on <t:{year_span.start_time}:d> and will end on <t:{year_span.end_time}:d>')

    # next year (original functionality)
    elif year == (current_year + 1):
        year_span = await get_year_span(year, guild=guild_config.id)
        if (elapsed_days % guild_config.epoch.length) == 0 and datetime.now().time() < guild_config.epoch.get_rollover_time():
            await ctx.respond(f'Happy New Year! Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

        else:
            await ctx.respond(f'Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

    # easter egg (far future)
    elif (guild_config.epoch.length * (year - current_year - 1)) > (365 * 80):
        await ctx.respond(f"Year {year} PC won't matter because we'll all be dead; try something sooner maybe")

    # check future years
    else:
        year_span = await get_year_span(year, guild=guild_config.id)
        await ctx.respond(f'Year {year} PC will start on <t:{year_span.start_time}:d>')


@year_group.command(name='search', description='Prints search query for timlining')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
async def year_search(ctx: ApplicationContext, year: int):
    guild_config = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild_config.id)
    year_span = await get_year_span(year, guild=guild_config.id)
    msg = []

    # invalid year input
    if year <= 0:
        await ctx.respond('Failed: Only years 1 PC or later are valid options', ephemeral=True)
        return

    elif (guild_config.epoch.length * (year - current_year - 1)) > (365 * 10):
        await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', "the only constant in the universe: the timeline isn't caught up that far"))
        return

    canon_channels = [*guild_config.channels.lore_channels, guild_config.channels.meta_chat, *guild_config.channels.canon_channels]

    # get a list of all the lore channels
    for channel_id in canon_channels:
        msg.append(f'in:{ctx.guild.get_channel(channel_id).name}')

    if year_span.start_time > 0:
        start = datetime.fromtimestamp(year_span.start_time, tz=config.timezone) - timedelta(days=1)
        msg.append(f'after:{start.strftime("%Y-%m-%d")}')

    if year_span.end_time > 0:
        end = datetime.fromtimestamp(year_span.end_time, tz=config.timezone) + timedelta(days=1)
        msg.append(f'before:{end.strftime("%Y-%m-%d")}')

    await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', ' '.join(msg)))


async def find_marker_link(year: int, channel: TextChannel) -> str:
    cfg = config.guild(channel.guild.id)
    marker = None

    # look for {year} or 'pc' or 'year' in message contents
    def has_year_marker(year: int, content: str) -> bool:
        content = content.lower().partition('\n')[0]

        if re.search(rf'\b{year}\b', content) or (year < 10 and re.search(rf'\b{year - 1}\b', content)):
            return 'pc' in content or 'year' in content
        else:
            return False

    # Check if its in the db
    if await YearMarker.exists(channel=channel.id, year=year):
        logger.debug(f'Hit cache for {year} PC in {channel.id}')
        marker = await YearMarker.get(channel=channel.id, year=year)

    else:
        # Fetch stored marker for that year
        guild_marker = await YearMarker.get(channel=cfg.id, year=year)
        if guild_marker is None:
            logger.error(f'No guild marker found for year {year} in {cfg.id}')
            return format_message_link(guild=cfg.id, channel=channel.id, message=0, relative=True)
        timestamp = snowflake_time(guild_marker.message)
        marker = YearMarker(channel=channel.id, message=0, year=year)
        logger.debug(f'Searching for {year} PC in {channel.id}')
        closest = SECONDS_PER_DAY

        # Search Channel History
        async for message in channel.history(around=timestamp, limit=15):
            # aim for closet message
            distance = abs((snowflake_time(message.id) - timestamp).total_seconds())

            if distance < closest:
                logger.debug(f'Closest found: {message.id} (off by {distance}s)')
                marker.message = message.id
                closest = distance

            # skip finding perfect match for meta-chat
            if channel.id not in cfg.channels.lore_channels:
                continue

            # try to find perfect match
            if message.author.id in cfg.users.markers and has_year_marker(year, message.content):
                logger.debug(f'Exact found: {message.id}')
                marker.message = message.id
                marker.exact = True
                break

        # were at our best guess, save here
        await marker.save()

    # Send message link
    return format_message_link(
        guild=cfg.id,
        channel=channel.id,
        message=marker.message,
        relative=(not marker.exact),
    )

@year_group.command(name='link', description='Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=TextChannel)
async def year_link(ctx: ApplicationContext, year: int, channel: TextChannel | None):
    cfg = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=cfg.id)

    canon_channels = [*cfg.channels.lore_channels, cfg.channels.meta_chat, *cfg.channels.canon_channels]

    if channel is None:
        channel = cast(TextChannel, ctx.guild.get_channel_or_thread(canon_channels[0]))

    # validate arguments
    if year < 1 or year > current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)

    # Skip if its a not a text channel (so we can be unspecific about canon_channels)
    elif channel.type != ChannelType.text:
        await ctx.respond(f'Failed: Command does not work on whatever {channel.mention} is', ephemeral=True)

    # validate as lore channel
    elif channel.id not in canon_channels:
        await ctx.respond('Failed: This command only works on lore channels', ephemeral=True)

    else:
        link = await find_marker_link(year, channel)
        await ctx.respond(f'{year} PC: {link}')

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(year_group)
