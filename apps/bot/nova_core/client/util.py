# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.util | generic utils."""

import colorsys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any, cast

import discord
import structlog
from discord.ext.commands import Context

import attu_logging
from nova_core.client.core import config


# --- initialization ---

logger = structlog.stdlib.get_logger(__name__)

# --- permissions check ---


def is_bot_owner(ctx: Context) -> bool:
    user_id = cast(discord.ApplicationContext, ctx).user.id
    return config.is_owner(user_id)


def is_authorized_guild(ctx: Context) -> bool:
    return ctx.guild.id in config.authorized_guilds


def has_announcements_role(ctx: Context) -> bool:
    """return True if the invoking member holds the configured announcements role."""
    try:
        gc = config.guild(ctx.guild.id)
    except Exception:
        logger.warning('announcements role lookup failed', guild_id=ctx.guild.id, exc_info=True)
        return False
    role_id = gc.roles.announcements
    if role_id == 0:
        return False
    app_ctx = cast(discord.ApplicationContext, ctx)
    return isinstance(app_ctx.author, discord.Member) and any(r.id == role_id for r in app_ctx.author.roles)


# --- decorators ---


def webhook_logging(scope: structlog.stdlib.BoundLogger) -> Callable:
    """catch exceptions and forward them to the error webhook.

    intentionally does not re-raise; the scheduler's own handler is not needed
    when the webhook already captures the error.
    """

    def decorator(func: Callable) -> Callable:
        async def wrapper(*args, **kwargs) -> Any:
            try:
                return await func(*args, **kwargs)

            except Exception as error:
                scope.error('decorated function raised', exc_info=True, func=func.__name__)
                await attu_logging.webhook.send_to_webhook(error)

        return wrapper

    return decorator


# --- logging context ---


@contextmanager
def event_log_context(**fields: object) -> Iterator[None]:
    """bind structlog contextvars for the duration of an event handler body.

    listen-style event handlers don't go through bot.before_invoke/after_invoke, so they need
    explicit binding. unbinds on exit so context doesn't leak into other tasks sharing the loop.
    """
    structlog.contextvars.bind_contextvars(**fields)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars(*fields.keys())


# --- theme ---


def theme_color() -> int:
    """return the bot theme color as an int, falling back to blurple"""
    if config.theme:
        return int(config.theme.bot_color.lstrip('#'), 16)
    return 0x5865F2  # discord blurple


def shift_hue(hex_color: str, degrees: float = 1.0) -> str:
    """shift the hue of a hex color by the given number of degrees and return a new hex string"""
    hex_clean = hex_color.lstrip('#')
    r, g, b = (int(hex_clean[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    h, lightness, s = colorsys.rgb_to_hls(r, g, b)
    h = (h + degrees / 360.0) % 1.0
    r2, g2, b2 = colorsys.hls_to_rgb(h, lightness, s)
    return f'#{round(r2 * 255):02x}{round(g2 * 255):02x}{round(b2 * 255):02x}'


# --- formatting ---


def format_message_link(guild: int, channel: int, message: int, relative: bool = False) -> str:
    return f'https://discord.com/channels/{guild}/{channel}/{message}' + ('[~]' if relative else '')


# for trimming to discord character length
def break_at_newline(text: str, maximum: int, end: str = '...\n') -> str:
    if len(text) <= maximum:
        return text

    lines = text.split('\n')
    result = ''

    for line in lines:
        # check if adding this line (with newline) plus the end marker would exceed maximum
        potential = result + line + '\n'
        if len(potential) + len(end) > maximum:
            # can't fit this line, return what we have so far with end marker
            return (result + end)[:maximum]

        result = potential

    # if we get here, we've included all lines but still need to add end marker
    return (result + end)[:maximum]
