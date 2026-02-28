"""
AttuBot - Embed Utilities
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime

import discord
from discord import Color, Embed

from attubot.util import theme_color


def make_embed(
    title: str,
    *,
    description: str | None = None,
    url: str | None = None,
    color: int | Color | None = None,
    footer: str | None = None,
    thumbnail: str | None = None,
    timestamp: bool | datetime = True,
) -> Embed:
    """create a discord embed with standard defaults.

    args:
        title: the embed title
        description: optional embed description
        url: optional url to link from the title
        color: embed color; defaults to theme_color()
        footer: optional footer text
        thumbnail: optional thumbnail image url
        timestamp: if True, uses current utc time; pass a datetime to use a specific time; False to omit
    """
    resolved_color = color if color is not None else theme_color()
    if isinstance(resolved_color, Color):
        resolved_color = resolved_color.value

    embed = Embed(
        title=title,
        description=description,
        url=url,
        color=resolved_color,
    )

    if footer is not None:
        embed.set_footer(text=footer)

    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)

    if timestamp is True:
        embed.timestamp = datetime.now(tz=UTC)
    elif isinstance(timestamp, datetime):
        embed.timestamp = timestamp

    return embed
