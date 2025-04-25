"""
AttuBot - Tasks
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import date, datetime, time
from typing import Never, cast

from discord import Bot, TextChannel
from discord.ext import commands, tasks

from attubot.calendar import format_year_line, get_year_status
from attubot.config import GuildConfig, NovaConfig
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import create_task, webhook_logging
from attubot.wiki import AttuWiki

logger = get_logger(__name__)

# --- New Year Handling ---

"""
Rewrite to support multiple guilds
"""
class NovaYearEvent(commands.Cog):
    bot: Bot

    def __init__(self, bot: Bot):
        self.bot = bot
        self.task = self.guild_event_dispatch.start()

    @tasks.loop(minutes=30)  # gets updated in before_loop, but we have to pass it *something*
    async def guild_event_dispatch(self):
        logger.debug(f'Task "guild_event_dispatch" triggered on {date.today()}, {datetime.now()}')

        for guild in NovaConfig.guilds.values():
            if guild.id not in NovaConfig.valid_guilds:
                continue

            if self.guild_event_dispatch.next_iteration.timetz() == guild.epoch.rollover_time:
                create_task(self.guild_event_check(guild))

    # starts update_loop_loop task after config loads; then holds the task start until the bot starts
    @guild_event_dispatch.before_loop
    async def wait_for_ready(self):
        await NovaConfig.wait_for_load()

        # Update the loop interval to match loaded guilds
        create_task(self.update_loop_loop())

        await self.bot.wait_until_ready()

    # task keeps the event intervals in sync with the guild config
    @webhook_logging(scope=logger)
    async def update_loop_loop(self) -> Never:
        while True:
            logger.info('Scheduling task "guild_event_dispatch" at rollover times')
            times: list[time] = []

            for guild in NovaConfig.guilds.values():
                if not guild.epoch.paused:
                    times.append(guild.epoch.rollover_time)

            self.guild_event_dispatch.change_interval(time=times)

            # sleep until next event time
            await NovaConfig.wait_for_reload()

    @webhook_logging(scope=logger)
    async def guild_event_check(self, guild: GuildConfig):
        elapsed_days, year = get_year_status(guild.id)
        epoch = guild.epoch

        if epoch.paused:
            logger.info(f'[{guild!s}] Skipping task - time paused')

        elif elapsed_days % epoch.length != 0:
            logger.info(f'[{guild!s}] Year {year + 1} PC: {epoch.length - (elapsed_days % epoch.length)} days away')

        elif year < (await YearMarker.total(guild.id)):
            logger.error(f'[{guild!s}] Already enough years; was event manually triggered?')

        else:
            logger.info(f'[{guild!s}] Proccessing guild event')
            await self.advance_year(guild, year)

    @webhook_logging(scope=logger)
    async def advance_year(self, cfg: GuildConfig, year: int):
        logger.info(f'[{cfg!s}] Happy New Year! Advancing to Year {year} PC')
        guild = self.bot.get_guild(self.guild)

        # --- Lore Channel Year Markers ---

        year_str = format_year_line(year)
        message_links = []

        for channel_id in cfg.channels.lore_channels:
            channel = guild.get_channel_or_thread(channel_id)
            message = await channel.send(year_str)

            # Save message ids to markers database
            await YearMarker.mark(year, message.id, channel=channel_id)

            if len(message_links) == 0:
                await YearMarker.mark(year, message.id, channel=cfg.id)

            # store links for later
            message_links.append(message.jump_url)

        # --- Increase Year VC ---

        year_vc = guild.get_channel_or_thread(cfg.channels.year_vc)
        await year_vc.edit(name=f'Current Year: {year} PC')

        # --- Edit Wiki ---

        wiki = AttuWiki()
        await wiki.authenticate(NovaConfig.wiki.user, NovaConfig.wiki.key)

        text = await wiki.get_page_contents(page_name=NovaConfig.wiki.page)
        updated_page = re.sub(r'Current Year: [\d]+ PC', f'Current Year: {year} PC', text, flags=re.IGNORECASE)

        await wiki.edit(NovaConfig.wiki.page, updated_page, f'Bumped to Year {year} PC')

        # --- Make Announcement ---

        channel = guild.get_channel_or_thread(cfg.channels.announcements)
        await channel.send(f'<@&{cfg.roles.announcements}> Year {year} PC. (weap)')

        # --- Send Year Links Message ---

        thread = guild.get_channel_or_thread(cfg.channels.year_links)
        await thread.send(year_str + '\n' + '\n'.join(message_links))

# --- Webhook Task ---

@webhook_logging(scope=logger)
async def error_hook_refresh(bot: Bot):
    if NovaConfig.test_mode:
        logger.debug('Application in test mode; skipping error hook refresh')
        return

    try:
        guild = bot.get_guild(NovaConfig.error_log[0])
        error_log = cast(TextChannel, guild.get_channel(NovaConfig.error_log[1]))

        webhooks = await error_log.webhooks()
        webhook_urls = [hook.url for hook in webhooks]

        # cleanup old urls
        for old in webhooks:
            if old.user == bot.user and old.url != NovaConfig.error_hook:
                logger.warn(f'Deleted old webhook: {old.name}-{old.id}')
                await old.delete()

        if NovaConfig.error_hook in webhook_urls:
            logger.debug('Existing error hook found; skipping refresh')
            return

        icon = await bot.user.display_avatar.read()
        hook = await error_log.create_webhook(name=bot.user.name, avatar=icon, reason='DoomBot Error Log')

        logger.info(f'Created new webhook: {hook.name}-{hook.id}')
        NovaConfig.error_hook = await NovaConfig.set('error_hook', hook.url)

    except Exception as err:
        logger.error(f'Failed acquiring new webhook for error log: {err}')

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_cog(NovaYearEvent(bot))
