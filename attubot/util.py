"""
AttuBot - Generic Utils
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from collections.abc import Callable
from typing import Any, cast

import discord
from discord.ext.commands import Context

from attubot.core import config
from attubot.logging import Logger, get_logger


# --- Initialization ---

logger = get_logger(__name__)

# --- Permissions Check ---


def is_bot_owner(ctx: Context) -> bool:
    user_id = cast(discord.ApplicationContext, ctx).user.id
    return config.is_owner(user_id)


def is_authorized_guild(ctx: Context) -> bool:
    return ctx.guild.id in config.authorized_guilds


def has_announcements_role(ctx: Context) -> bool:
    """Return True if the invoking member holds the configured announcements role."""
    try:
        gc = config.guild(ctx.guild.id)
    except Exception:
        return False
    role_id = gc.roles.announcements
    if role_id == 0:
        return False
    app_ctx = cast(discord.ApplicationContext, ctx)
    return isinstance(app_ctx.author, discord.Member) and any(r.id == role_id for r in app_ctx.author.roles)


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


# --- Theme ---


def theme_color() -> int:
    """return the bot theme color as an int, falling back to blurple"""
    if config.theme:
        return int(config.theme.bot_color.lstrip('#'), 16)
    return 0x5865F2  # discord blurple


# --- Formatting ---


# util to make discord message links
def format_message_link(guild: int, channel: int, message: int, relative: bool = False) -> str:
    return f'https://discord.com/channels/{guild}/{channel}/{message}' + ('[~]' if relative else '')


# for trimming to discord character length
def break_at_newline(text: str, maximum: int, end: str = '...\n') -> str:
    if len(text) <= maximum:
        return text

    lines = text.split('\n')
    result = ''

    for line in lines:
        # Check if adding this line (with newline) plus the end marker would exceed maximum
        potential = result + line + '\n'
        if len(potential) + len(end) > maximum:
            # Can't fit this line, return what we have so far with end marker
            return (result + end)[:maximum]

        result = potential

    # If we get here, we've included all lines but still need to add end marker
    return (result + end)[:maximum]
