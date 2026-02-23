"""
attu-bot - {background tasks, fixes, wiki edits} triggered by other events
See also: ./commands/run.py

author(s): @jhnhnck <john@jhnhnck.com>
license: apache, version 2.0; See /LICENSE
"""

from asyncio import Task, create_task, sleep
from collections.abc import Coroutine
from typing import cast
from uuid import uuid4

import discord
from discord import ChannelType, TextChannel

from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Async Background Jobs ---

class JobWorker:
    """
    Job Worker.
    Provides some functions for storing jobs and dealing with them
    """
    storage: set[Task]

    def __init__(self) -> None:
        self.storage = set()

    # @former: create_task
    # from <https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task>
    def add_job(self, coro: Coroutine, name: str | None = None, priority: bool = True):
        if not name:
            name = 'Task[' + uuid4().hex[:16] + ']'

        async def wait_wrapper():
            if not priority:
                await sleep(self.current_delay)
            await coro

        logger.info(f'Starting task: {name}')
        task = create_task(wait_wrapper(), name=name)

        self.storage.add(task)

        task.add_done_callback(self.storage.discard)

    @property
    def count(self) -> int:
        from attubot import bot
        return len(self.storage) + len(bot.cogs)

    @property
    def running_tasks(self) -> list[str]:
        from attubot import bot
        names: list[str] = []

        for task in self.storage:
            names.append(task.get_name())

        for name, _ in bot.cogs.items():
            names.append(name)

        return names

    @property
    def current_delay(self) -> float:
        return 30.0

# --- jobs ---

async def job_backfill_channel(channel_id: int, guild_id: int, interaction: discord.Interaction | None = None):
    """scan a channel and backfill any messages not already stored.

    args:
        channel_id: id of the discord channel to scan
        guild_id: id of the guild the channel belongs to
        interaction: optional interaction to edit with results when complete
    """
    from attubot import bot
    from attubot.messages import _get_repo, build_message_doc

    repo = _get_repo()
    channel = bot.get_channel(channel_id)

    if channel is None:
        logger.error(f'fix messages: channel {channel_id} not found in cache')
        if interaction is not None:
            await interaction.edit_original_response(content=f'Error: channel {channel_id} not found')
        return

    stored = 0
    backfilled = 0

    try:
        async for message in channel.history(oldest_first=True, limit=None):
            existing = await repo.get(message.id)
            if existing is not None:
                stored += 1
            else:
                try:
                    doc = await build_message_doc(message)
                    await repo.upsert(doc)
                    backfilled += 1
                except Exception as err:
                    logger.warn(f'fix messages: failed to store message {message.id}: {err}')

            total = stored + backfilled
            if total % 1000 == 0:
                logger.debug(f'fix messages #{channel.name}: scanned {total:,} messages, {backfilled:,} backfilled so far')

    except discord.Forbidden:
        logger.warn(f'fix messages: no permission to read history in #{channel.name} ({channel_id})')
        if interaction is not None:
            await interaction.edit_original_response(content=f'No permission to read history in <#{channel_id}>')
        return
    except Exception as err:
        logger.error(f'fix messages: error scanning channel {channel_id}: {err}')
        if interaction is not None:
            await interaction.edit_original_response(content=f'Error scanning <#{channel_id}> - check logs')
        return

    total = stored + backfilled
    logger.info(f'fix messages #{channel.name}: done - {total:,} scanned, {backfilled:,} backfilled')

    if interaction is not None:
        await interaction.edit_original_response(content=f'Done! Scanned {total:,} messages in <#{channel_id}>: {stored:,} already stored, {backfilled:,} backfilled')


async def job_fix_author_names(guild_id: int, interaction: discord.Interaction | None = None, user_id: int | None = None):
    """resolve current global usernames and bulk-update author_name on all stored messages.

    args:
        guild_id: guild to operate on
        interaction: optional interaction to edit with results when complete
        user_id: if set, only update messages from this single author
    """
    from attubot import bot
    from attubot.messages import _get_repo, _global_username

    repo = _get_repo()

    if user_id is not None:
        author_ids = [user_id]
    else:
        author_ids = await repo.distinct_author_ids(guild_id)
        logger.info(f'fix author_names: found {len(author_ids)} distinct authors for guild {guild_id}')

    updated_msgs = 0
    resolved = 0
    not_found = 0

    for i, author_id in enumerate(author_ids):
        try:
            user = bot.get_user(author_id) or await bot.fetch_user(author_id)
            name = _global_username(user)
            count = await repo.update_author_name(author_id, name)
            updated_msgs += count
            resolved += 1
        except Exception as err:
            not_found += 1
            logger.warn(f'fix author_names: could not resolve user {author_id}: {err}')

        if (i + 1) % 50 == 0 and interaction is not None:
            await interaction.edit_original_response(content=f'Progress: {i + 1}/{len(author_ids)} users processed...')

    summary = f'Done - {resolved} users resolved, {updated_msgs:,} messages updated'
    if not_found:
        summary += f', {not_found} users not found'

    logger.info(f'fix author_names: {summary} (guild {guild_id})')

    if interaction is not None:
        await interaction.edit_original_response(content=summary)


async def job_construct_year_links(guild_id: int):
    from attubot import bot, config
    from attubot.calendar import format_year_line, get_year_span
    from attubot.commands.year import find_marker_link
    from attubot.years import Year

    cfg = config.guild(guild_id)
    guild = bot.get_guild(cfg.id)
    lore_channels: list[TextChannel] = []

    # Get all years from DB instead of computing current year
    all_years = await Year.all_for_guild(guild_id)
    current_year = all_years[-1].year if all_years else 1

    # collecting these so were not constantly querying them later
    for channel_id in cfg.channels.lore_channels:
        channel = guild.get_channel_or_thread(channel_id)

        if channel is not None and channel.type == ChannelType.text:
            lore_channels.append(cast(TextChannel, channel))

    async def generate_links_block(year: int) -> str:
        year_str = format_year_line(year, level=2)
        marker_links = []

        for channel in lore_channels:
            jump_url = await find_marker_link(year, channel)
            marker_links.append(jump_url)

        span = await get_year_span(year, guild_id)

        return (
            f'{year_str}\n'
            f'<t:{span.start_time}:f> - <t:{span.end_time}:f>\n'
            f'{"\n".join(marker_links)}'
        )

    # check channel for errors
    thread = guild.get_channel_or_thread(cfg.channels.year_links)

    if thread is None:
        logger.error(f'Could not find channel {cfg.channels.year_links} for construction')
        return

    year_idx = 1
    async for message in thread.history(limit=None, oldest_first=True):
        if message.author.id != bot.user.id:
            await message.add_reaction('<:rockball:1308981475114225694>')
            continue

        block = await generate_links_block(year_idx)

        if message.content != block:
            logger.warn(f'Index {year_idx} is wrong for {message.jump_url}; replacing block')
            await message.edit(content=block)

        year_idx += 1

    while year_idx <= current_year:
        logger.warn(f'Index {year_idx} is missing; sending new block')
        block = await generate_links_block(year_idx)
        await thread.send(content=block)
        year_idx += 1
