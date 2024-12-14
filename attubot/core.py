"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
import traceback
from datetime import date, datetime
from os import getenv

import discord
from discord import Permissions
from discord.ext import tasks

from attubot import __version__
from attubot.config import Config
from attubot.logging import get_logger
from attubot.util import format_year_line, get_year_span, get_year_status, move_epoch
from attubot.wiki import AttuWiki

# --- Initialization ---

logger = get_logger(__name__)
logger.info('Initializing...')

intents = discord.Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

build_format = '%a %b %d %H:%M:%S %Z %Y'

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

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Debug Option to Run', input_type=str)
async def debug(ctx, option: str):
    options = ['version', 'year_stats', 'force_error']
    options.sort()

    if ctx.user.id != Config.bot_owner:
        await ctx.respond("You're not my real dad!")
        return

    if option == 'version':
        build_time = datetime.strptime(getenv('BUILD_TIME'), build_format)

        await ctx.respond('\n'.join([
            f'Version: {__version__}',
            f'Container Build Time: <t:{int(build_time.timestamp())}:f>',
        ]))

    elif option == 'year_stats':
        elapsed_days, current_year = get_year_status()
        year_span = get_year_span(current_year)

        await ctx.respond('\n'.join([
            f'Current Year: {current_year} PC',
            f'Year Span: <t:{year_span.start_time}:f> to <t:{year_span.end_time}:f> ({year_span.duration} days)',
            f'Attu Epoch: {Config.epoch_year} PC at <t:{Config.epoch_time}:f>',
            f'Time Since Epoch: {elapsed_days} Days',
            f'Next Task Iteration: <t:{int(task_year_check.next_iteration.timestamp())}:f>',
        ]))

    elif option == 'force_error':
        await ctx.respond('Forcing an error message')
        math = 10 / 0  # noqa: F841

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='option', required=True, description='Admin Option to Run', input_type=str)
@discord.commands.option(name='number', required=False, description='Arguments', input_type=int)
async def admin(ctx, option: str, number):
    options = ['force_year', 'time_dilate', 'time_pause', 'time_resume']
    options.sort()

    if ctx.user.id != Config.bot_owner:
        await ctx.respond("You're not my real dad!")
        return

    if option == 'force_year':
        forced_year = len(Config.timestamps) + 1
        _, year = get_year_status()

        logger.info(f'Weap. Year forced by admin: expected: {year} doing: {forced_year}')
        await ctx.respond('Weap. No longer going to try my best, just forcing new year instead')
        await advance_year(forced_year)

    elif option == 'time_pause':
        await ctx.respond('The passage of time has been stopped')
        Config.pause_time()

    elif option == 'time_resume':
        move_epoch(Config.epoch_length)

        await ctx.respond(f'The passage of time has been resumed with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')
        Config.resume_time()

    elif option == 'time_dilate':
        if number is None:
            await ctx.respond('Failed: Submit dilation amount (in days) in number field', ephemeral=True)
            return

        if Config.time_paused:
            Config.set_epoch_length(number)
            await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year**')
        else:
            move_epoch(number)
            await ctx.respond(f'The passage of time has been set to **{Config.epoch_length} days per year** with Attu epoch moved to **{Config.epoch_year} PC** at **<t:{Config.epoch_time}:f>**')

    else:
        await ctx.respond(f'Failed: Options are {", ".join(options)}', ephemeral=True)

@bot.slash_command(guilds_only=True, default_member_permissions=Permissions.all())
@discord.commands.option(name='user', required=True, description='Wiki Username (case sensitive probably)', input_type=str)
@discord.commands.option(name='reason', required=True, description='Reason for blocking', input_type=str)
async def wiki_block(ctx, user, reason):
    # TODO: allow sending a link to the user profile instead
    await ctx.respond(f'Blocking user "{user}": {reason}')

    wiki = AttuWiki()
    wiki.authenticate(Config.wiki_user, Config.wiki_key)
    wiki.block(user, f'{reason} (on behalf of {ctx.user.global_name})')

# --- New Year Handling ---

@tasks.loop(time=Config.rollover_time)
async def task_year_check():
    logger.debug(f'task_year_check() Task triggered on {date.today()}, {datetime.now()}')

    try:
        await check_for_new_year()
    except Exception as error:
        send_to_error_log(error)

async def check_for_new_year():
    elapsed_days, year = get_year_status()

    if Config.time_paused:
        logger.info('The passage of time has been paused; skipping task')

    elif elapsed_days % Config.epoch_length != 0:
        logger.info(f'Days Remaining Until Year {year + 1} PC: {Config.epoch_length - (elapsed_days % Config.epoch_length)}')

    elif year < len(Config.timestamps):
        logger.error('Already enough years; was event manually triggered?')

    else:
        await advance_year(year)

async def advance_year(year):
    guild = bot.get_guild(Config.attu_guild)

    logger.info(f'Happy New Year! Advancing to Year {year} PC')

    # --- Lore Channel Year Markers ---

    year_str = format_year_line(year)
    message_links = []

    for channel_id in Config.lore_channels:
        channel = guild.get_channel(channel_id)
        message = await channel.send(year_str)
        message_links.append(message.jump_url)

    # Save timestamp to config file
    Config.add_timestamp(message.id)

    # --- Increase Year VC ---

    year_vc = guild.get_channel(Config.year_vc)
    await year_vc.edit(name=f'Current Year: {year} PC')

    # --- Edit Wiki ---

    wiki = AttuWiki()
    wiki.authenticate(Config.wiki_user, Config.wiki_key)

    text = wiki.get_page_contents(Config.wiki_page)
    updated_page = re.sub(r'Current Year: [\d]+ PC', f'Current Year: {year} PC', text, flags=re.IGNORECASE)

    wiki.edit(Config.wiki_page, updated_page, f'Bumped to Year {year} PC')

    # --- Make Announcement ---

    channel = guild.get_channel(Config.announce_channel)
    await channel.send(f'<@&{Config.announce_role}> Year {year} PC. (weap)')

    # --- Send Year Links Message ---

    doom_forum = guild.get_channel(Config.doom_forum)
    thread = doom_forum.get_thread(Config.year_link_thread)
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

    logger.info('Starting bot...')
    bot.run(Config.bot_token)
