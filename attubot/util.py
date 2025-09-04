"""
AttuBot - Generic Utils
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""
#ruff: noqa: PLC0415

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any, cast

import discord
from discord.ext.commands import Context

from attubot.logging import Logger, get_logger

# --- Initialization ---

logger = get_logger(__name__)

# --- Permissions Check ---

def is_bot_owner(ctx: Context) -> bool:
    from attubot.config import NovaConfig

    user_id = cast(discord.ApplicationContext, ctx).user.id
    return NovaConfig.is_owner(user_id)


def is_authorized_guild(ctx: Context) -> bool:
    from attubot.config import NovaConfig

    return ctx.guild.id in NovaConfig.authorized_guilds

# --- Async Background Jobs ---

background_tasks: set[asyncio.Task] = set()

# from <https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task>
def create_task(coro: Coroutine):
    task = asyncio.create_task(coro)

    background_tasks.add(task)

    task.add_done_callback(background_tasks.discard)


def get_task_count() -> int:
    from attubot.config import NovaConfig

    if NovaConfig._bot is not None:
        return len(background_tasks) + len(NovaConfig._bot.cogs)
    else:
        return len(background_tasks)

# --- Decorators ---

def webhook_logging(scope: Logger) -> Callable:
    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)

            except Exception as error:
                await scope.send_to_webhook(error)

        return wrapper
    return decorator

# --- Formatting ---

# util to make discord message links
def format_message_link(guild: int, channel: int, message: int, relative: bool = False) -> str:
    return f'https://discord.com/channels/{guild}/{channel}/{message}{" [~]" if relative else ""}'


# for trimming to discord character length
def break_at_newline(text: str, maximum: int, end: str = '...\n') -> str:
    if len(text) > maximum:
        lines = text[:(maximum + len(end))].split('\n')
        _ = lines.pop()  # remove mangled last line
        result = ''

        for line in lines:
            holding = f'f{result}{line}\n'

            if len(holding) + len(end) > maximum:
                return result + end

            result += line + '\n'

    return text
