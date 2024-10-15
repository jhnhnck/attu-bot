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
from collections import namedtuple
from types import SimpleNamespace

import discord
from discord import Permissions
from discord.ext import tasks
from discord.utils import snowflake_time

from attubot import __version__
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
trigger_time = time(17, 0, tzinfo=ZoneInfo(getenv('TZ')))

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
    time_diff_sec = (datetime.combine(date.today(), trigger_time) - datetime.fromtimestamp(config.epoch_time).astimezone()).total_seconds()
    elapsed_days = int(time_diff_sec / 86400)
    year = config.epoch_year + (elapsed_days // config.epoch_length)

    if (elapsed_days % config.epoch_length) == 0 and datetime.now().time() < trigger_time:
        year -= 1

    return elapsed_days, year

def get_next_year():
    if config.time_paused:
        return datetime.fromtimestamp(0).astimezone()

    elapsed_days, _ = get_year_status()
    new_date = datetime.combine(date.today(), trigger_time) + timedelta((config.epoch_length - elapsed_days) % config.epoch_length)

    if (elapsed_days % config.epoch_length) == 0 and datetime.now().time() >= trigger_time:
        new_date += timedelta(days=config.epoch_length)

    return new_date

def get_year_span(year: int):
    result = SimpleNamespace(start_time=0, end_time=0, duration=0)

    _, current_year = get_year_status()
    next_year = get_next_year()

    # Invalid Years
    if year <= 0:
        logger.error(f'get_year() requested with invalid year: {year}')

    # Past Years
    elif year < current_year:
        result.start_time = int(snowflake_time(config.timestamps[year - 1]).timestamp())
        result.end_time = int(snowflake_time(config.timestamps[year]).timestamp())

    # Current Year
    elif year == current_year:
        result.start_time = int(snowflake_time(config.timestamps[year - 1]).timestamp())
        result.end_time = int(next_year.timestamp())

    # Next Year
    elif year == (current_year + 1):
        result.start_time = int(next_year.timestamp())
        result.end_time = int((next_year + timedelta(days=(config.epoch_length * (year - current_year - 1)))).timestamp()) if not config.time_paused else 0

    # Future Years
    elif not config.time_paused:
        result.start_time = int((next_year + timedelta(days=(config.epoch_length * (year - current_year - 1)))).timestamp())
        result.end_time = int((next_year + timedelta(days=(config.epoch_length * (year - current_year)))).timestamp())

    result.duration = round((result.end_time - result.start_time) / 86400)
    return result

def reset_epoch():
    elapsed_days, year = get_year_status()
    week_offset = 0

    # has the epoch already been reset
    if config.epoch_year > len(config.timestamps):
        logger.info('Epoch already been reset; not doing again')
        return

    # offset for if you immediately resume after pausing
    if year <= len(config.timestamps):
        week_offset = (elapsed_days % config.epoch_length) // 7

    # make next week if today is friday already
    if date.today().weekday() == 4:
        week_offset += 1

    config.set_epoch(datetime.combine(date.today() + timedelta(((4 - date.today().weekday()) % 7) + (week_offset * 7)), trigger_time), len(config.timestamps) + 1)
    logger.info(f'New Epoch Set: {config.epoch_year} PC at {config.epoch_time}')

async def send_to_error_log(error):
    global bot

    guild = bot.get_guild(config.jhn_guild)
    error_log = guild.get_channel(config.error_log_channel)

    tb_str = ''.join(traceback.format_tb(error.__traceback__))

    await error_log.send(f'**{str(error)}**\n```\n{tb_str}```')

    logger.error(error + '\n' + tb_str)

# --- Slash Commands ---

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int)
async def check_year(ctx, year: int):
    elapsed_days, current_year = get_year_status()
    year_span = get_year_span(current_year if year is None else year)

    # invalid year input
    if year <= 0:
        await ctx.respond('Failed: Only years 1 PC or later are valid options', ephemeral=True)

    # prior years
    elif year < current_year:
        await ctx.respond(f'Year {year} PC lasted for {year_span.duration} days, starting on <t:{year_span.start_time}:d> and ending on <t:{year_span.end_time}:d>')

    # check if time is paused first
    elif config.time_paused:
        await ctx.respond('Sorry! New Years is cancelled until further notice')

    # current year
    elif year == current_year:
        await ctx.respond(f'Year {year} PC will last for {year_span.duration} days, which started on <t:{year_span.start_time}:d> and will end on <t:{year_span.end_time}:d>')

    # next year (original functionality)
    elif year == (current_year + 1):
        if (elapsed_days % config.epoch_length) == 0 and datetime.now().time() < trigger_time:
            await ctx.respond(f'Happy New Year! Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

        else:
            await ctx.respond(f'Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

    # easter egg (far future)
    elif (config.epoch_length * (year - current_year - 1)) > (365 * 80):
        await ctx.respond(f'Year {year} PC won\'t matter because we\'ll all be dead; try something sooner maybe', ephemeral=True)

    # check future years
    else:
        await ctx.respond(f'Year {year} PC will start on <t:{year_span.start_time}:d>')

@bot.slash_command(guilds_only=True)
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=discord.TextChannel)
async def link_year(ctx, year: int, channel: discord.TextChannel):
    channel_id = 0

    if channel is None:
        channel_id = config.lore_channels[3]

    elif channel.id not in config.lore_channels and channel.id != config.meta_chat_channel:
        await ctx.respond('Failed: Channel is not a lore channel.', ephemeral=True)
        return

    else:
        channel_id = channel.id

    if year < 1 or year > len(config.timestamps):
        await ctx.respond(f'Failed: Pick a year between 1 and {len(config.timestamps)}.', ephemeral=True)
        return

    # Send message link
    await ctx.respond(f'{year} PC: https://discord.com/channels/{config.attu_guild}/{channel_id}/{config.timestamps[year - 1]}')

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Debug Option to Run', input_type=str)
async def debug(ctx, option: str):
    global config

    options = ['version', 'year_stats', 'force_error']
    options.sort()

    if ctx.user.id != config.bot_owner:
        await ctx.respond('You\'re not my real dad!')
        return

    if option == 'version':
        build_time = datetime.strptime(getenv("BUILD_TIME"), build_format)

        await ctx.respond('\n'.join([
            f'Version: {__version__}',
            f'Container Build Time: <t:{int(build_time.timestamp())}:f>',
        ]))

    elif option == 'year_stats':
        elapsed_days, year = get_year_status()
        next_year = get_next_year()

        await ctx.respond('\n'.join([
            f'Current Year: {year} PC',
            f'Attu Epoch: {config.epoch_year} PC at <t:{config.epoch_time}:f>',
            f'Next Year: <t:{int(next_year.timestamp())}:f>',
            f'Time Since Epoch: {elapsed_days} Days',
            f'Next Task Iteration: <t:{int(task_year_check.next_iteration.timestamp())}:f>'
        ]))

    elif option == 'force_error':
        await ctx.respond('Forcing an error message')
        math = 10 / 0

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Admin Option to Run', input_type=str)
@discord.commands.option(name='number', required=False, description='Arguments', input_type=int)
async def admin(ctx, option: str, number):
    global config

    options = ['force_year', 'time_dilate', 'time_pause', 'time_resume']
    options.sort()

    if ctx.user.id != config.bot_owner:
        await ctx.respond('You\'re not my real dad!')
        return

    if option == 'force_year':
        forced_year = len(config.timestamps) + 1
        _, year = get_year_status()

        logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
        await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
        await advance_year(forced_year)

    elif option == 'time_pause':
        await ctx.respond('The passage of time has been stopped')
        config.time_paused = True

    elif option == 'time_resume':
        reset_epoch()

        await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{config.epoch_year} PC** at **<t:{config.epoch_time}:f>**')
        config.time_paused = False

    elif option == 'time_dilate':
        if number is None:
            await ctx.respond('Failed: Submit dilation amount in number field', ephemeral=True)
            return

        config.set_epoch_length(number)

        if config.time_paused:
            await ctx.respond(f'The passage of time has been set to **{config.epoch_length} days per year**')
        else:
            reset_epoch()
            await ctx.respond(f'The passage of time has been set to **{config.epoch_length} days per year** with Attu epoch moved to **{config.epoch_year} PC** at **<t:{config.epoch_time}:f>**')

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

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
    elapsed_days, year = get_year_status()

    if config.time_paused:
        logger.info('The passage of time has been paused; skipping task')

    elif elapsed_days % config.epoch_length != 0:
        logger.info(f'Days Remaining Until Year {year + 1} PC: {config.epoch_length - (elapsed_days % config.epoch_length)}')

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
