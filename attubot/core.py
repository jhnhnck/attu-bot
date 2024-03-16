"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv
from datetime import datetime, date, time
from pytz import timezone
import re

import discord
from discord import Permissions
from discord.ext import tasks

from attubot.config import Config
from attubot.logging import get_logger
logger = get_logger(__name__)

from attubot.wiki import AttuWiki

# --- Initialization ---

logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)
config = Config(getenv('BOT_CONFIG_FILE'))

separators = ["<","=","+","\>","/","&",":","$","\*","%","@", "⁂", "xXx","\\\\","?","^","\|","\~", '-']
flipped_separators = { '<': '>', '\>': '<', '/': '\\\\', '\\\\': '/' }

build_format = '%a %b %d %H:%M:%S %Z %Y'

# --- Utilities ---

def format_year_line(year):
    global separators, escaped_separators, flipped_separators

    sep = separators[year % len(separators)]

    if len(sep) > 2:
        return f'# {sep} Year {year} PC {sep}'
    if sep in flipped_separators:
        return f'# {sep * 3} Year {year} PC {flipped_separators[sep] * 3}'
    else:
        return f'# {sep * 3} Year {year} PC {sep * 3}'

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
async def check_year(ctx):
    global bot, config
    guild = bot.get_guild(config.guild)

    # --- Checks ---

    days_since_epoch =  (date.today() - date.fromtimestamp(config.epoch_time)).days
    year = config.epoch_year + (days_since_epoch // 14)

    if days_since_epoch % 14 == 1:
        await ctx.respond(f'{14 - (days_since_epoch % 14)} Day Remaining Until Year {year + 1} PC')
    elif days_since_epoch % 14 != 0:
        await ctx.respond(f'{14 - (days_since_epoch % 14)} Days Remaining Until Year {year + 1} PC')
    else:
        await ctx.respond(f'Happy New Year! Advancing to Year {year} PC at <t:1708207200:t>')

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='channel', required=True, description='Lore Channel', input_type=discord.TextChannel)
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int)
async def link_year(ctx, channel: discord.TextChannel, year: int):
    global bot, config

    if channel.id not in config.lore_channels and channel.id != config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel.', ephemeral=True)
        return

    if year < 1 or year > len(config.timestamps):
        await ctx.respond(f'Failed: Pick a year between 1 and {len(config.timestamps)}.', ephemeral=True)
        return

    # Send message link
    await ctx.respond(f'https://discord.com/channels/{config.guild}/{channel.id}/{config.timestamps[year - 1]}')

@bot.slash_command(guilds_only=True)
async def build_date(ctx):
    build_time = datetime.strptime(getenv("BUILD_TIME"), build_format)
    await ctx.respond(f'Container Build Time: <t:{int(build_time.timestamp())}:f>')

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
async def force_year(ctx):

    await ctx.respond('Trying my best to manually trigger task!')
    await check_for_new_year()

# --- Tasks ---

@tasks.loop(time=time(17, 0, tzinfo=timezone('America/New_York')))
async def check_for_new_year():
    global bot, config
    guild = bot.get_guild(config.guild)

    # --- Checks ---

    days_since_epoch = (date.today() - date.fromtimestamp(config.epoch_time)).days
    year = config.epoch_year + (days_since_epoch // 14)

    if days_since_epoch % 14 != 0:
        logger.info(f'Days Remaining Until Year {year + 1} PC: {14 - (days_since_epoch % 14)}')
        return

    elif year <= len(config.timestamps):
        logger.error(f'Already enough years; was event manually triggered?')
        return

    else:
        logger.info(f'Happy New Year! Advancing to Year {year} PC')

    # --- Lore Channel Year Markers ---

    year_str = format_year_line(year)
    message_links = []

    for channel_id in config.lore_channels:
        channel = guild.get_channel(channel_id)
        message = await channel.send(year_str)
        message_links.append(message.jump_url)

    # Save timestamp to config file
    config.add_timestamp(message.id)

    # --- Increase Year VC ---

    year_vc = guild.get_channel(config.year_vc)
    await year_vc.edit(name=f'Current Year: {year} PC')

    # --- Edit Wiki ---

    wiki = AttuWiki()
    wiki.authenticate(config.wiki_user, config.wiki_key)

    text = wiki.get_page_contents(config.wiki_page)
    updated_page = re.sub(r'Current Year: [\d]+ PC', f'Current Year: {year} PC', text, flags=re.IGNORECASE)

    wiki.edit(config.wiki_page, updated_page, f'Bumped to Year {year} PC')

    # --- Make Annoucement ---
    channel = guild.get_channel(config.announce_channel)
    await channel.send(f'<@&{config.announce_role}> Year {year} PC. (weap)')

    # --- Send Year Links Message

    doom_forum = guild.get_channel(config.doom_forum)
    thread = doom_forum.get_thread(config.year_link_thread)
    await thread.send(year_str + '\n' + '\n'.join(message_links))

# --- Events ---

@bot.event
async def on_ready():
    perms = '207952'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    check_for_new_year.start()

@bot.event
async def on_message(message):
    if message.channel.id == config.activity_channel and message.content.startswith('[DoomBot]'):
        await message.add_reaction('💖')


"""
@bot.event
async def on_message(message):
    logger.info(f'Message from {message.author}: {message.content}')
"""

# --- Trigger Function ---

def start_bot_loop():
    global bot, config

    config.load_from_file()

    logger.info('Starting bot...')
    bot.run(config.bot_token)
