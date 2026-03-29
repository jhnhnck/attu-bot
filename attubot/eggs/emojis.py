"""
AttuBot - Egg emoji rendering and Discord upload helpers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord

from attubot.client.logo import svg_to_png
from attubot.eggs.data import rarities
from attubot.logging import get_logger


logger = get_logger(__name__)


async def render_egg(rarity: str) -> bytes:
    """Render the egg SVG for the given rarity to PNG bytes."""
    from attubot.client.core import config
    svg_path = config.path.parent / 'static' / 'emoji' / 'egg.svg'
    svg_text = svg_path.read_text()
    # swap the class on the root <g> element to select the correct color theme
    svg_text = svg_text.replace('class="common"', f'class="{rarity}"', 1)
    return await svg_to_png(svg_text, height=128, width=128)


_progress_segments = ['left_full', 'left_empty', 'none_full', 'none_empty', 'right_full', 'right_empty']


async def ensure_egg_emojis(guild: discord.Guild) -> dict[str, discord.Emoji]:
    """Ensure all five rarity egg emojis exist on guild; create any that are missing.

    Returns a mapping of rarity -> Emoji.
    """
    existing = {e.name: e for e in guild.emojis}
    result: dict[str, discord.Emoji] = {}

    for rarity in rarities:
        key = f'{rarity}_egg'
        if key not in existing:
            logger.info(f'creating emoji {key} on guild {guild.id}')
            png = await render_egg(rarity)
            emoji = await guild.create_custom_emoji(name=key, image=png)
        else:
            emoji = existing[key]
            logger.debug(f'emoji {key} already exists on guild {guild.id}')

        result[rarity] = emoji

    return result


async def ensure_progress_emojis(guild: discord.Guild) -> dict[str, discord.Emoji]:
    """Ensure all 6 progress bar emojis exist on guild; create any missing.

    Returns mapping of segment_key -> Emoji.
    Keys: left_full, left_empty, none_full, none_empty, right_full, right_empty.
    """
    from attubot.client.core import config
    assets_dir = config.path.parent / 'static' / 'emoji'
    existing = {e.name: e for e in guild.emojis}
    result: dict[str, discord.Emoji] = {}

    for segment in _progress_segments:
        name = f'progress_{segment}'
        if name not in existing:
            logger.info(f'creating emoji {name} on guild {guild.id}')
            png = (assets_dir / f'{name}.png').read_bytes()
            emoji = await guild.create_custom_emoji(name=name, image=png)
        else:
            emoji = existing[name]
            logger.debug(f'emoji {name} already exists on guild {guild.id}')

        result[segment] = emoji

    return result


def render_progress_bar(filled: int, total: int, segments: int = 10) -> str:
    """Render a Discord emoji progress bar string.

    segments = total bar width (1 left cap + middles + 1 right cap).
    Falls back to unicode blocks if progress_emojis not configured.
    """
    from attubot.client.core import config

    emojis = config.theme.progress_emojis
    middles = segments - 2
    units = min(round(filled / total * segments), segments) if total > 0 else 0

    def _seg(key: str) -> str:
        emoji_id = emojis.get(key)
        return f'<:pb:{emoji_id}>' if emoji_id else ('■' if 'full' in key else '□')

    left = _seg('left_full') if units >= 1 else _seg('left_empty')
    mids = [_seg('none_full') if units >= i + 2 else _seg('none_empty') for i in range(middles)]
    right = _seg('right_full') if units == segments else _seg('right_empty')
    return left + ''.join(mids) + right
