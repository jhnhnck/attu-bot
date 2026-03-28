"""
AttuBot - Egg emoji rendering and Discord upload helpers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord

from attubot.client.core import config
from attubot.client.logo import svg_to_png
from attubot.eggs.data import rarities
from attubot.logging import get_logger


logger = get_logger(__name__)


async def render_egg(rarity: str) -> bytes:
    """Render the egg SVG for the given rarity to PNG bytes."""
    svg_path = config.path.parent / 'eggs' / 'egg.svg'
    svg_text = svg_path.read_text()
    # swap the class on the root <g> element to select the correct color theme
    svg_text = svg_text.replace('class="common"', f'class="{rarity}"', 1)
    return await svg_to_png(svg_text, height=128, width=128)


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
