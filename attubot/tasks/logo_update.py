"""
AttuBot - Logo Update Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import colorsys
from datetime import datetime, timedelta
from random import random

import discord

from attubot import bot, config
from attubot.client.calendar import get_year_span, get_year_status
from attubot.client.logo import generate_png
from attubot.client.util import webhook_logging
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class LogoUpdateTask(BaseTask):
    """Recurring task to keep the logo in sync with theme settings.

    Runs on a fixed 2.5-minute interval. Color is derived from HSL values stored in theme config.
    """

    name: str = 'LogoUpdateEvent'
    interval: timedelta | None = timedelta(minutes=2, seconds=30)

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()
        await asyncio.sleep(10 * 60)  # don't start immediately

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Update the bot and guild icons based on theme rotation."""
        theme = config.theme
        epoch = config.primary().epoch

        # calculate new rotation
        if not epoch.paused:
            _, current_year = get_year_status()
            year_span = await get_year_span(current_year)
            elapsed_minutes = (datetime.now().astimezone() - datetime.fromtimestamp(year_span.start_time).astimezone()).total_seconds() // 60
            new_rotation = round(elapsed_minutes / (year_span.duration * 1440) * 360, 2)

        else:
            new_rotation = theme.rotation + (random() * theme.max_rate)

        logger.info(f'changing icon rotation from {theme.rotation} to {new_rotation}')

        # derive hex color from hsl
        hue = (new_rotation % 360) / 360.0
        r, g, b = colorsys.hls_to_rgb(hue, config.theme.lightness, config.theme.saturation)
        computed_color = f'#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}'

        # generate new icons
        bot_avatar = await generate_png(new_rotation, computed_color)
        guild_icon = await generate_png(new_rotation, theme.guild_color)

        # edit guild and bot with new logos
        guild = bot.get_guild(config.primary_guild) or await bot.fetch_guild(config.primary_guild)
        await guild.edit(icon=guild_icon, reason='logo update task')
        await bot.user.edit(avatar=bot_avatar)

        # update the emoji too. why not?
        emoji_name = guild.name.replace(' ', '_').lower()

        for emoji in guild.emojis:
            if emoji_name in emoji.name:
                logger.debug(f'clearing old emoji "{emoji.name}"')
                await emoji.delete()
                break

        await guild.create_custom_emoji(name=emoji_name, image=guild_icon, reason='logo update task')

        # update the bot_color role to match the current theme color
        role_id = config.primary().roles.bot_color
        if role_id:
            role = guild.get_role(role_id)
            if role is not None:
                await role.edit(color=discord.Color(int(computed_color.lstrip('#'), 16)), reason='logo update task')
                logger.debug(f'updated bot_color role {role.name} to {computed_color}')

        # store new rotation and computed hex (keeps web ui and util.py in sync)
        config.theme.rotation = new_rotation % 360
        config.theme.bot_color = computed_color
        await config.theme.save()


# singleton instance for registration
logo_update_task = LogoUpdateTask()
