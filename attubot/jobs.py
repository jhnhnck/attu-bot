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

async def job_compress_year_markers():
    pass


async def job_construct_year_links(guild_id: int):
    from attubot import bot, config
    from attubot.calendar import format_year_line, get_year_span, get_year_status
    from attubot.commands.year import find_marker_link

    cfg = config.guild(guild_id)
    guild = bot.get_guild(cfg.id)
    lore_channels: list[TextChannel] = []
    _, current_year = get_year_status(guild=cfg.id)

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
