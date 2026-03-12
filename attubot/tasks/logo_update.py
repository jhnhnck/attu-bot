"""
AttuBot - Logo Update Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import math
from datetime import datetime, timedelta
from random import random

from attubot import bot, config
from attubot.client.calendar import get_year_span, get_year_status
from attubot.client.logo import generate_png
from attubot.client.util import webhook_logging
from attubot.logging import get_logger
from attubot.tasks.base import BaseTask


logger = get_logger(__name__)


class LogoUpdateTask(BaseTask):
    """Recurring task to keep the logo in sync with theme settings.

    Runs once per 1/360th of the primary guild's current in-game year, aligned
    to the year's start (rollover) time so that each tick corresponds to exactly
    one degree of rotation.
    """

    name: str = 'LogoUpdateEvent'
    interval: timedelta | None = None  # dynamic scheduling via next_run()

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()
        await asyncio.sleep(10 * 60)  # don't start immediately

    async def next_run(self) -> datetime | None:
        """Return the datetime for the next 1/360th-year boundary."""
        await config.wait_for_load()
        epoch = config.primary().epoch

        if not epoch.paused:
            _, current_year = get_year_status()
            year_span = await get_year_span(current_year)
            duration = year_span.duration if year_span.duration > 0 else epoch.length
            start_time = year_span.start_time
        else:
            duration = epoch.length
            start_time = None

        # segment length in seconds
        segment_seconds = duration * 86400 / 360

        now = datetime.now().astimezone()

        if start_time is not None:
            # align to year start so ticks are evenly spaced from rollover
            elapsed = now.timestamp() - start_time
            current_segment = math.floor(elapsed / segment_seconds)
            next_tick = datetime.fromtimestamp(start_time + (current_segment + 1) * segment_seconds).astimezone()
        else:
            next_tick = now + timedelta(seconds=segment_seconds)

        logger.debug(f'next logo update scheduled for {next_tick.isoformat()} ({segment_seconds / 60:.2f}min intervals)')
        return next_tick

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

        logger.info(f'Changing icon rotation from {theme.rotation} to {new_rotation}')

        # generate new icons
        bot_avatar = await generate_png(new_rotation, theme.bot_color)
        guild_icon = await generate_png(new_rotation, theme.guild_color)

        # edit guild and bot with new logos
        guild = bot.get_guild(config.primary_guild)
        await guild.edit(icon=guild_icon, reason='logo update task')
        await bot.user.edit(avatar=bot_avatar)

        # update the emoji too. why not?
        emoji_name = guild.name.replace(' ', '_').lower()

        for emoji in guild.emojis:
            if emoji_name in emoji.name:
                logger.debug(f'Clearing old emoji "{emoji.name}"')
                await emoji.delete()
                break

        await guild.create_custom_emoji(name=emoji_name, image=guild_icon, reason='logo update task')

        # store new rotation in config
        config.theme.rotation = new_rotation % 360
        await config.theme.save()


# singleton instance for registration
logo_update_task = LogoUpdateTask()
