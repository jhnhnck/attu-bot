"""
AttuBot - Utilities
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from datetime import date, datetime, timedelta
from typing import Coroutine, cast

import discord
from discord.ext.commands import Context
from pydantic import BaseModel

from attubot.config import Config, NovaConfig
from attubot.logging import get_logger
from attubot.markers import YearMarker

# --- Initialization ---

logger = get_logger(__name__)

separators = ['<', '=', '+', r'\>', '/', '&', ':', '$', r'\*', '%', '@', '⁂', 'xXx', '\\\\', '?', '^', r'\|', r'\~', '-']
flipped_separators = {'<': '>', r'\>': '<', '/': '\\\\', '\\\\': '/'}

# --- Permissions Check ---

def is_bot_owner(ctx: Context) -> bool:
    user_id = cast(discord.ApplicationContext, ctx).user.id
    return NovaConfig.is_owner(user_id)


def is_authorized_guild(ctx: Context) -> bool:
    return ctx.guild.id in NovaConfig.authorized_guilds

# --- Components ---

class AttuYear(BaseModel):
    start_time: int
    end_time: int
    duration: int

# --- Async Background Jobs ---

background_tasks: set[asyncio.Task] = set()

# from <https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task>
def create_task(coro: Coroutine):
    task = asyncio.create_task(coro)

    background_tasks.add(task)

    task.add_done_callback(background_tasks.discard)

# --- Utilities ---

def format_year_line(year) -> str:
    sep = separators[year % len(separators)]

    if len(sep) > 2:
        return f'# {sep} Year {year} PC {sep}'
    if sep in flipped_separators:
        return f'# {sep * 3} Year {year} PC {flipped_separators[sep] * 3}'
    else:
        return f'# {sep * 3} Year {year} PC {sep * 3}'


def get_year_status() -> tuple[int, int]:
    today = datetime.combine(date.today(), Config.rollover_time)
    epoch = datetime.combine(datetime.fromtimestamp(Config.epoch_time).astimezone(), Config.rollover_time)
    time_diff_sec = (today - epoch).total_seconds()

    elapsed_days = int(time_diff_sec / 86400)
    year = Config.epoch_year + (elapsed_days // Config.epoch_length)

    if (elapsed_days % Config.epoch_length) == 0 and datetime.now().time() < Config.rollover_time:
        year -= 1

    return elapsed_days, year


def get_next_year() -> datetime:
    if Config.time_paused:
        return datetime.fromtimestamp(0).astimezone()

    elapsed_days, _ = get_year_status()
    new_date = datetime.combine(date.today(), Config.rollover_time) + timedelta((Config.epoch_length - elapsed_days) % Config.epoch_length)

    if (elapsed_days % Config.epoch_length) == 0 and datetime.now().time() >= Config.rollover_time:
        new_date += timedelta(days=Config.epoch_length)

    return new_date


async def get_year_span(year: int) -> AttuYear:
    result = AttuYear(start_time=0, end_time=0, duration=0)

    _, current_year = get_year_status()
    next_year = get_next_year()

    # Invalid Years
    if year <= 0 or year > 10000:
        logger.error(f'get_year() requested with invalid year: {year}')
        year = 10000 if year > 0 else 1

    # Past Years
    elif year < current_year:
        result.start_time = await YearMarker.timestamp(year)
        result.end_time = await YearMarker.timestamp(year + 1)

    # Current Year
    elif year == current_year:
        result.start_time = await YearMarker.timestamp(year)
        result.end_time = int(next_year.timestamp())

    # Next Year
    elif year == (current_year + 1):
        result.start_time = int(next_year.timestamp())
        result.end_time = int((next_year + timedelta(days=(Config.epoch_length * (year - current_year)))).timestamp()) if not Config.time_paused else 0

    # Future Years
    elif not Config.time_paused:
        result.start_time = int((next_year + timedelta(days=(Config.epoch_length * (year - current_year - 1)))).timestamp())
        result.end_time = int((next_year + timedelta(days=(Config.epoch_length * (year - current_year)))).timestamp())

    result.duration = round((result.end_time - result.start_time) / 86400)
    return result


# TODO: Shouldn't this be on the guild object
async def move_epoch(length: int, guild_id=NovaConfig.primary_guild):
    elapsed_days, current_year = get_year_status()
    year_span = await get_year_span(current_year)
    guild = NovaConfig.guild(guild_id)

    # handle picking new year time if paused
    if guild.epoch.paused:
        friday = date.today() + timedelta(days=(11 - date.today().weekday()) % 7)

        # check if already passed trigger time
        if date.today().weekday() == 4 and datetime.now().time() >= guild.epoch.rollover_time:
            friday += timedelta(days=7)

        await guild.set_epoch(datetime.combine(friday, guild.epoch.rollover_time), current_year + 1)

    # new length longer than current year has lasted, just extend
    elif length >= (elapsed_days % guild.epoch.length):
        await guild.set_epoch(datetime.combine(datetime.fromtimestamp(year_span.start_time).astimezone(), guild.epoch.rollover_time).timestamp(), current_year)

    # wait for current year to complete first
    else:
        await guild.set_epoch(year_span.end_time, current_year + 1)

    await guild.set_year_length(length)
    logger.info(f'New Epoch Set: {guild.epoch.year} PC at <t:{guild.epoch.time}:f> with year length of {guild.epoch.length}')


# look for {year} or 'pc' or 'year' in message contents
def has_year_marker(year: int, content: str) -> bool:
    content = content.lower()

    if str(year) in content or (year < 10 and str(year - 1) in content):
        return 'pc' in content or 'year' in content
    else:
        return False


# util to make discord message links
def format_message_link(guild, channel, message, relative=False) -> str:
    return f'https://discord.com/channels/{guild}/{channel}/{message}{" [~]" if relative else ""}'


# create a new error hook
async def error_hook_refresh(bot: discord.Bot):
    if NovaConfig.test_mode:
        logger.debug('Application in test mode; skipping error hook refresh')
        return

    try:
        guild = bot.get_guild(NovaConfig.error_log[0])
        error_log = cast(discord.TextChannel, guild.get_channel(NovaConfig.error_log[1]))

        webhooks = await error_log.webhooks()
        webhook_urls = [hook.url for hook in webhooks]

        # cleanup old urls
        for old in webhooks:
            if old.user == bot.user and old.url != NovaConfig.error_hook:
                logger.warn(f'Deleted old webhook: {old.name}-{old.id}')
                await old.delete()

        if NovaConfig.error_hook in webhook_urls:
            logger.debug('Existing error hook found; skipping refresh')
            return

        icon = await bot.user.display_avatar.read()
        hook = await error_log.create_webhook(name=bot.user.name, avatar=icon, reason='DoomBot Error Log')

        logger.info(f'Created new webhook: {hook.name}-{hook.id}')
        NovaConfig.error_hook = await NovaConfig.set('error_hook', hook.url)


    except Exception as err:
        logger.error(f'Failed acquiring new webhook for error log: {err}')
