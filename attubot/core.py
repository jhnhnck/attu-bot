"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import traceback
from datetime import datetime

import discord

from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import get_year_span, get_year_status

# --- Initialization ---

logger = get_logger(__name__)
logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- Error Handling ---

async def send_to_error_log(error):
    guild = bot.get_guild(Config.jhn_guild)
    error_log = guild.get_channel(Config.error_log_channel)

    tb_str = ''.join(traceback.format_tb(error.__traceback__))

    await error_log.send(f'**{error}**\n```\n{tb_str}```')

    logger.error(str(error) + '\n' + tb_str)

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int)
async def check_year(ctx, year: int):
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

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=discord.TextChannel)
async def link_year(ctx, year: int, channel: discord.TextChannel):
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

# --- Events ---

@bot.event
async def on_ready():
    perms = '207952'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    logger.info('Pushing commands to Discord')
    await bot.sync_commands()

@bot.event
async def on_message(message):
    if message.channel.id == Config.activity_channel and message.content.startswith('[DoomBot]'):
        if 'blocked' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')

@bot.event
async def on_application_command_error(ctx, error):
    await send_to_error_log(error)

"""
@bot.event
async def on_message(message):
    logger.info(f'Message from {message.author}: {message.content}')
"""

# --- Trigger Function ---

def start_bot_loop():
    Config.init()

    logger.info('Loading extensions...')
    bot.load_extension('attubot.tasks')
    bot.load_extension('attubot.admin')

    logger.info('Starting bot...')
    bot.run(Config.bot_token)
