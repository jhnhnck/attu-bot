"""
AttuBot - User Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime
import re

import discord
from discord import Permissions
from discord.ext import commands

from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import get_year_span, get_year_status, is_authorized_guild
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- Year Commands ---

year_group = discord.SlashCommandGroup('year', description='Utlities related to current, past or future years')

@year_group.command(name='check', guilds_only=True, description='Prints out information related to a specified year; if not specified, year defaults to the next year')
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int, min_value=1)
async def year_check(ctx, year: int):
    elapsed_days, current_year = get_year_status()
    year = year if year is not None else (current_year + 1)
    year_span = get_year_span(year)

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
        await ctx.respond(f"Year {year} PC won't matter because we'll all be dead; try something sooner maybe", ephemeral=True)

    # check future years
    else:
        await ctx.respond(f'Year {year} PC will start on <t:{year_span.start_time}:d>')

@year_group.command(name='link', guilds_only=True, description='Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=discord.TextChannel)
async def link_year(ctx, year: int, channel: discord.TextChannel):
async def year_link(ctx, year: int, channel: discord.TextChannel):
    elapsed_days, current_year = get_year_status()
    channel_id = 0

    if channel is None:
        channel_id = Config.lore_channels[3]

    elif channel.id not in Config.lore_channels and channel.id != Config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel.', ephemeral=True)
        return

    else:
        channel_id = channel.id

    if year < 1 or year > len(Config.timestamps):
        await ctx.respond(f'Failed: Pick a year between 1 and {len(Config.timestamps)}.', ephemeral=True)
        return

    # Send message link
    await ctx.respond(f'{year} PC: https://discord.com/channels/{Config.attu_guild}/{channel_id}/{Config.timestamps[year - 1]}')

@discord.slash_command(guilds_only=True, description='Search the wiki for relevent pages; defaults to top result')
# --- Wiki Commands ---

wiki_group = discord.SlashCommandGroup('wiki', description='Utlities for managing and querying the wiki')

@wiki_group.command(name='lookup', guilds_only=True, description='Search the wiki for relevent pages; defaults to top result')
@discord.commands.option(name='query', required=True, description='Search Query', input_type=str)
@discord.commands.option(name='limit', required=False, description='Max Number of Results', input_type=int, default=1, min_value=1, max_value=10)
async def lookup(ctx, query: str, limit: int):
async def wiki_lookup(ctx, query: str, limit: int):
    wiki = AttuWiki()
    pages = wiki.search(query, limit)
    logger.info(f'{query} {limit}')

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

    bot.add_application_command(check_year)
    bot.add_application_command(year_group)
    bot.add_application_command(wiki_group)
