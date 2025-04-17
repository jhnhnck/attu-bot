"""
AttuBot - Generic Utils
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from collections.abc import Coroutine
from typing import cast

import discord
from discord.ext.commands import Context

from attubot.logging import get_logger

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

# --- Formatting ---

# util to make discord message links
def format_message_link(guild: int, channel: int, message: int, relative: bool = False) -> str:
    return f'https://discord.com/channels/{guild}/{channel}/{message}{" [~]" if relative else ""}'
