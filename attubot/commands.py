"""
AttuBot - User Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord import Permissions
from discord.ext import commands
from discord.utils import snowflake_time

from attubot.config import Config
from attubot.logging import get_logger
from attubot.markers import YearMarker, markers_get
from attubot.util import format_message_link, get_year_span, get_year_status, has_year_marker, is_authorized_guild
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Year Commands ---

year_group = discord.SlashCommandGroup('year', description='Utlities related to current, past or future years')

@year_group.command(name='check', guilds_only=True, description='Prints out information related to a specified year; if not specified, year defaults to the next year')
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int, min_value=1)
async def year_check(ctx, year: int):
    elapsed_days, current_year = get_year_status()
    year = year if year is not None else (current_year + 1)
    year_span = await get_year_span(year)

    # invalid year input
    if year <= 0:
        await ctx.respond('Failed: Only years 1 PC or later are valid options', ephemeral=True)

    # prior years
    elif year < current_year:
        await ctx.respond(f'Year {year} PC lasted for {year_span.duration} days, starting on <t:{year_span.start_time}:d> and ending on <t:{year_span.end_time}:d>')

    # check if time is paused first
    elif Config.time_paused:
        await ctx.respond('Sorry! New Years is cancelled until further notice')

    # current year
    elif year == current_year:
        await ctx.respond(f'Year {year} PC will last for {year_span.duration} days, which started on <t:{year_span.start_time}:d> and will end on <t:{year_span.end_time}:d>')

    # next year (original functionality)
    elif year == (current_year + 1):
        if (elapsed_days % Config.epoch_length) == 0 and datetime.now().time() < Config.rollover_time:
            await ctx.respond(f'Happy New Year! Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

        else:
            await ctx.respond(f'Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

    # easter egg (far future)
    elif (Config.epoch_length * (year - current_year - 1)) > (365 * 80):
        await ctx.respond(f"Year {year} PC won't matter because we'll all be dead; try something sooner maybe")

    # check future years
    else:
        await ctx.respond(f'Year {year} PC will start on <t:{year_span.start_time}:d>')

@year_group.command(name='search', guilds_only=True, description='Prints search query for timlining')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
async def year_search(ctx, year: int):
    _, current_year = get_year_status()
    year_span = await get_year_span(year)
    guild = ctx.bot.get_guild(Config.attu_guild)
    msg = []

    # invalid year input
    if year <= 0:
        await ctx.respond('Failed: Only years 1 PC or later are valid options', ephemeral=True)
        return

    elif (Config.epoch_length * (year - current_year - 1)) > (365 * 10):
        await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', "the only constant in the universe: the timeline isn't caught up that far"))
        return

    # get a list of all the lore channels
    for channel_id in [*Config.lore_channels, Config.meta_chat_channel, 1001837934590312458, 1175719558032654356]:
        msg.append(f'in:{guild.get_channel(channel_id).name}')

    tz = ZoneInfo('America/New_York')

    if year_span.start_time > 0:
        start = datetime.fromtimestamp(year_span.start_time, tz=tz) - timedelta(days=1)
        msg.append(f'after:{start.strftime("%Y-%m-%d")}')

    if year_span.end_time > 0:
        end = datetime.fromtimestamp(year_span.end_time, tz=tz) + timedelta(days=1)
        msg.append(f'before:{end.strftime("%Y-%m-%d")}')

    await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', ' '.join(msg)))

@year_group.command(name='link', guilds_only=True, description='Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=discord.TextChannel)
async def year_link(ctx, year: int, channel: discord.TextChannel):
    _, current_year = get_year_status()
    marker = None

    if channel is None:
        guild = ctx.bot.get_guild(Config.attu_guild)
        channel = guild.get_channel(Config.lore_channels[0])

    # validate as lore channel
    if channel.id not in Config.lore_channels and channel.id != Config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel', ephemeral=True)
        return

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    # Check if its in the db
    if await YearMarker.exists(channel=channel.id, year=year):
        logger.debug(f'Hit cache for {year} PC in {channel.id}')
        marker = await YearMarker.get(channel=channel.id, year=year)

    # Fetch stored marker for that year
    else:
        timestamp = await markers_get(year, date=True)
        marker = YearMarker(channel=channel.id, message=0, year=year)
        logger.debug(f'Searching for {year} PC in {channel.id}')
        closest = 86400

        # Search Channel History
        async for message in channel.history(around=timestamp, limit=15):
            # aim for closet message
            distance = abs((snowflake_time(message.id) - timestamp).total_seconds())

            if distance < closest:
                logger.debug(f'Closest found: {message.id} (off by {distance}s)')
                marker.message = message.id
                closest = distance

            # skip finding perfect match for meta-chat
            if channel.id == Config.meta_chat_channel:
                continue

            # try to find perfect match
            if message.author.id in Config.users.markers and has_year_marker(year, message.content):
                logger.debug(f'Exact found: {message.id}')
                marker.message = message.id
                marker.exact = True
                break

    # Send message link
    await ctx.respond(f'{year} PC: {format_message_link(Config.attu_guild, channel.id, marker.message, relative=(not marker.exact))}')
    await marker.save()

# --- Wiki Commands ---

wiki_group = discord.SlashCommandGroup('wiki', description='Utlities for managing and querying the wiki')

@wiki_group.command(name='lookup', guilds_only=True, description='Search the wiki for relevent pages; defaults to top result')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
@discord.commands.option(name='limit', required=False, description='Max Number of Results', input_type=int, default=1, min_value=1, max_value=10)
async def wiki_lookup(ctx, query: str, limit: int):
    wiki = AttuWiki()
    pages = wiki.search(query, limit)

    # Handle no results
    if len(pages) == 0:
        await ctx.respond('Oops, no results! <:rockball_player:1308977543034048552>')
        return

    # Get wiki page format
    site_info = wiki.site_info()
    fmt = f"{Config.wiki_endpoint}{site_info['articlepath']}"

    # Build response
    if len(pages) == 1:
        await ctx.respond(fmt.replace('$1', pages[0]['key']))

    else:
        msg = [f'## Top Results for "{query}"']

        for page in pages:
            msg.append(f"1. [{page['title']}](<{fmt.replace('$1', page['key'])}>)")

        await ctx.respond('\n'.join(msg))

@wiki_group.command(name='block', guilds_only=True, default_member_permissions=Permissions.all(), description='Blocks a specified user from the wiki (Admin only)')
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
@commands.check(is_authorized_guild)
async def wiki_block(ctx, user, reason):
    # check if link to the user
    extract = re.search(r'User:(.*)$', user)

    if extract is not None:
        user = extract[1]

    await ctx.respond(f'Blocking user [{user}]: {reason}')

    wiki = AttuWiki()
    wiki.authenticate(Config.wiki_user, Config.wiki_key)
    wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(year_group)
    bot.add_application_command(wiki_group)
