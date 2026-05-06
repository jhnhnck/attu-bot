"""
AttuBot - Embed Utilities
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime

from discord import Color, Embed

from attubot.client.util import theme_color


def ui_emoji(name: str, fallback: str = '') -> str:
    """Format a custom UI emoji from the theme config, or return fallback."""
    from attubot.client.core import config

    if config.theme is None:
        return fallback
    emoji_id = config.theme.ui_emojis.get(name)
    if emoji_id:
        return f'<:{name}:{emoji_id}>'
    return fallback


def make_embed(
    title: str | None = None,
    *,
    description: str | None = None,
    url: str | None = None,
    color: int | Color | None = None,
    footer: str | None = None,
    thumbnail: str | None = None,
    author_name: str | None = None,
    author_icon_url: str | None = None,
    author_url: str | None = None,
    timestamp: bool | datetime = True,
) -> Embed:
    """create a discord embed with standard defaults.

    args:
        title: optional embed title
        description: optional embed description
        url: optional url to link from the title
        color: embed color; defaults to theme_color()
        footer: optional footer text
        thumbnail: optional thumbnail image url
        author_name: optional author display name shown above the title
        author_icon_url: optional icon shown next to the author name
        author_url: optional url to link from the author name
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

    if author_name is not None:
        embed.set_author(name=author_name, icon_url=author_icon_url, url=author_url)

    if footer is not None:
        embed.set_footer(text=footer)

    if thumbnail is not None:
        embed.set_thumbnail(url=thumbnail)

    if timestamp is True:
        embed.timestamp = datetime.now(tz=UTC)
    elif isinstance(timestamp, datetime):
        embed.timestamp = timestamp

    return embed
