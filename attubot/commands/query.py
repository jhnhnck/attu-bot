"""
AttuBot - Query Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import datetime

import discord
from discord import MessageType
from discord.ext import commands

from attubot.logging import get_logger
from attubot.util import get_year_span, get_year_status, is_bot_owner

logger = get_logger(__name__)

# --- Query Commands ---

query_group = discord.SlashCommandGroup('query', description="Performs searches for specific messages if that's your thing")

@query_group.command(name='pins', guilds_only=True, description='Finds all the "pinned a message" messages in a channel')
@discord.commands.option(name='channel', required=True, description='Channel', input_type=discord.TextChannel)
@commands.check(is_bot_owner)
async def query_pins(ctx, channel: discord.TextChannel):
    _, current_year = get_year_status()
    pins = []

    # this might take a bit so send message to not timeout
    logger.info(f'Querying pins in channel {channel.id}')
    res = await ctx.respond('Searching...')

    # for year 1 thru current year
    for year in range (1, current_year + 1):
        logger.info(f'Year {year} PC:')
        if year != current_year:
            continue

        year_span = get_year_span(year)
        start_time = datetime.fromtimestamp(year_span.start_time if year > 1 else 0).astimezone()
        end_time = datetime.fromtimestamp(year_span.end_time).astimezone()

        async for message in channel.history(after=start_time, before=end_time, limit=None):
            if message.type == MessageType.pins_add:
                logger.info(f'Found pin_add in {year} PC at {message.jump_url} -> {message.reference}')
                pins.append(f'{year} PC: {message.reference}')

    res.edit(content=f'## Pins in <#{channel.id}>\n' + '\n'.join(pins))

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(query_group)
