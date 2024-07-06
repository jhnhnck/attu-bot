"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv
from datetime import datetime, timedelta, date, time
from zoneinfo import ZoneInfo
import re
import traceback

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
trigger_time = time(17, 0, tzinfo=ZoneInfo('America/New_York'))

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

def get_year_status():
    time_since_epoch = datetime.now() - datetime.fromtimestamp(config.epoch_time)
    year = config.epoch_year + (time_since_epoch.days // 14)

    return time_since_epoch, year

async def send_to_error_log(error):
    global bot

    guild = bot.get_guild(config.jhn_guild)
    error_log = guild.get_channel(config.error_log_channel)

    tb_str = ''.join(traceback.format_tb(error.__traceback__))

    await error_log.send(f'**{str(error)}**\n```\n{tb_str}```')

    logger.error(error + '\n' + tb_str)

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
async def check_year(ctx):
    time_since_epoch, year = get_year_status()

    if config.time_paused:
        await ctx.respond('Sorry! New Years is cancelled until further notice')

    elif time_since_epoch.days % 14 != 0:
        await ctx.respond(f'Advancing to Year {year} PC <t:{int(datetime.combine(date.today(), trigger_time).timestamp())}:R>')

    else:
        await ctx.respond(f'Happy New Year! Advancing to Year {year} PC <t:{int(datetime.combine(date.today(), trigger_time).timestamp())}:R>')

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='channel', required=True, description='Lore Channel', input_type=discord.TextChannel)
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int)
async def link_year(ctx, channel: discord.TextChannel, year: int):
    if channel.id not in config.lore_channels and channel.id != config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel.', ephemeral=True)
        return

    if year < 1 or year > len(config.timestamps):
        await ctx.respond(f'Failed: Pick a year between 1 and {len(config.timestamps)}.', ephemeral=True)
        return

    # Send message link
    await ctx.respond(f'https://discord.com/channels/{config.attu_guild}/{channel.id}/{config.timestamps[year - 1]}')

@bot.slash_command(guilds_only=True)
async def build_date(ctx):
    build_time = datetime.strptime(getenv("BUILD_TIME"), build_format)
    await ctx.respond(f'Container Build Time: <t:{int(build_time.timestamp())}:f>')

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Admin Option to Run', input_type=str)
async def admin(ctx, option: str):
    global config

    if ctx.user.id != config.bot_owner:
        await ctx.respond('You\'re not my real dad!')
        return

    if option == 'force_year':
        forced_year = len(config.timestamps) + 1
        _, year = get_year_status()

        logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
        await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
        await advance_year(forced_year)

    elif option == 'trigger_check':
        await ctx.respond(f'Next `task_year_check()` Task iteration expected on <t:{int(task_year_check.next_iteration.timestamp())}:f>')

    elif option == 'date_check':
        await ctx.respond(f'Current Time is <t:{int(datetime.now().timestamp())}:f>')

    elif option == 'time_pause':
        await ctx.respond('The passage of time has been stopped')
        config.time_paused = True

    elif option == 'time_resume':
        config.set_epoch(datetime.combine(date.today() + timedelta((4 - date.today().weekday()) % 7), trigger_time), len(config.timestamps) + 1)

        await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to {config.epoch_year} PC at <t:{config.epoch_time}:f>')
        config.time_paused = False

    elif option == 'force_error':
        await ctx.respond('Forcing an error message')
        math = 10 / 0

    else:
        await ctx.respond('Failed: Options are date_check, force_error, force_year, time_pause, time_resume, and trigger_check', ephemeral=True)

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
async def wiki_block(ctx, user, reason):
    await ctx.respond(f'Blocking user: {user}', ephemeral=True)

    wiki = AttuWiki()
    wiki.authenticate(config.wiki_user, config.wiki_key)
    wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- New Year Handling ---

@tasks.loop(time=trigger_time)
async def task_year_check():
    logger.debug(f'task_year_check() Task triggered on {date.today()}, {datetime.now()}')

    try:
        await check_for_new_year()
    except Exception as error:
        send_to_error_log(error)

async def check_for_new_year():
    time_since_epoch, year = get_year_status()

    if config.time_paused:
        logger.info('The passage of time has been paused; skipping task')

    elif time_since_epoch.days % 14 != 0:
        logger.info(f'Days Remaining Until Year {year + 1} PC: {14 - (time_since_epoch.days % 14)}')

    elif year < len(config.timestamps):
        logger.error('Already enough years; was event manually triggered?')

    else:
        await advance_year(year)

async def advance_year(year):
    global bot, config
    guild = bot.get_guild(config.attu_guild)

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

    # --- Make Announcement ---

    channel = guild.get_channel(config.announce_channel)
    await channel.send(f'<@&{config.announce_role}> Year {year} PC. (weap)')

    # --- Send Year Links Message ---

    doom_forum = guild.get_channel(config.doom_forum)
    thread = doom_forum.get_thread(config.year_link_thread)
    await thread.send(year_str + '\n' + '\n'.join(message_links))

# --- Events ---

@bot.event
async def on_ready():
    perms = '207952'

    logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
    logger.info(f'Add to a server:\n\thttps://discordapp.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

    task_year_check.start()

@bot.event
async def on_message(message):
    if message.channel.id == config.activity_channel and message.content.startswith('[DoomBot]'):
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
    global bot, config

    config.load_from_file()

    logger.info('Starting bot...')
    bot.run(config.bot_token)
