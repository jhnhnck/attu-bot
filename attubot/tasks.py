"""
AttuBot - Tasks
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import date, datetime

from discord import Bot
from discord.ext import commands, tasks

from attubot.config import Config
from attubot.core import send_to_webhook
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import format_year_line, get_year_status
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- New Year Handling ---

class NewYearEvent(commands.Cog):
    bot: Bot

    def __init__(self, bot):
        self.bot = bot
        self.task_year_check.start()

    @tasks.loop(time=Config.rollover_time)
    async def task_year_check(self):
        logger.debug(f'task_year_check() Task triggered on {date.today()}, {datetime.now()}')

        try:
            await self.check_for_new_year()
        except Exception as error:
            await send_to_webhook(error)

    @task_year_check.before_loop
    async def wait_for_ready(self):
        await self.bot.wait_until_ready()

    async def check_for_new_year(self):
        elapsed_days, year = get_year_status()

        if Config.time_paused:
            logger.info('The passage of time has been paused; skipping task')

        elif elapsed_days % Config.epoch_length != 0:
            logger.info(f'Days Remaining Until Year {year + 1} PC: {Config.epoch_length - (elapsed_days % Config.epoch_length)}')

        elif year < (await YearMarker.total()):
            logger.error('Already enough years; was event manually triggered?')

        else:
            await self.advance_year(year)

    async def advance_year(self, year: int):
        guild = self.bot.get_guild(Config.attu_guild)

        logger.info(f'Happy New Year! Advancing to Year {year} PC')

        # --- Lore Channel Year Markers ---

        year_str = format_year_line(year)
        message_links = []

        for channel_id in Config.lore_channels:
            channel = guild.get_channel_or_thread(channel_id)
            message = await channel.send(year_str)

            # Save message ids to markers database
            await YearMarker.mark(year, message.id, channel=channel_id)

            if len(message_links) == 0:
                await YearMarker.mark(year, message.id)

            # store links for later
            message_links.append(message.jump_url)

        # --- Increase Year VC ---

        year_vc = guild.get_channel_or_thread(Config.year_vc)
        await year_vc.edit(name=f'Current Year: {year} PC')

        # --- Edit Wiki ---

        wiki = AttuWiki()
        wiki.authenticate(Config.wiki_user, Config.wiki_key)

        text = wiki.get_page_contents(Config.wiki_page)
        updated_page = re.sub(r'Current Year: [\d]+ PC', f'Current Year: {year} PC', text, flags=re.IGNORECASE)

        wiki.edit(Config.wiki_page, updated_page, f'Bumped to Year {year} PC')

        # --- Make Announcement ---

        channel = guild.get_channel_or_thread(Config.announce_channel)
        await channel.send(f'<@&{Config.announce_role}> Year {year} PC. (weap)')

        # --- Send Year Links Message ---

        thread = guild.get_channel_or_thread(Config.year_link_thread)
        await thread.send(year_str + '\n' + '\n'.join(message_links))

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_cog(NewYearEvent(bot))
