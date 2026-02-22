"""
AttuBot - Guild Year Rollover Task
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import re
from datetime import datetime

from attubot import bot, config
from attubot.calendar import format_year_line, get_next_year, get_year_status
from attubot.config import GuildConfig
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.tasks.base import BaseTask
from attubot.tasks.jobs import job_construct_year_links
from attubot.util import webhook_logging
from attubot.wiki import get_wiki
from attubot.years import Year

logger = get_logger(__name__)


class NovaYearTask(BaseTask):
    """Wakes up at the exact time of the next guild rollover and advances the year.

    Uses dynamic scheduling via next_run() - sleeps until the earliest rollover
    time across all valid guilds rather than polling on a fixed interval.
    """

    name: str = 'NovaYearEvent'
    interval = None

    async def on_start(self) -> None:
        await config.wait_for_load()
        await bot.wait_until_ready()

    async def next_run(self) -> datetime | None:
        """Return the earliest upcoming rollover time across all valid guilds."""
        earliest: datetime | None = None

        for guild_id, guild in config.guilds.items():
            if guild_id not in config.valid_guilds:
                continue
            if guild.epoch.paused:
                continue

            candidate = get_next_year(guild_id)

            if earliest is None or candidate < earliest:
                earliest = candidate

        if earliest is None:
            # all guilds are paused - check again in 30 minutes
            from datetime import timedelta

            return datetime.now().astimezone() + timedelta(minutes=30)

        return earliest

    @webhook_logging(scope=logger)
    async def run(self) -> None:
        """Check all guilds for year rollover eligibility."""
        for guild_id, guild in config.guilds.items():
            if guild_id not in config.valid_guilds:
                continue

            await self._rollover_guild(guild)

    @webhook_logging(scope=logger)
    async def _rollover_guild(self, cfg: GuildConfig) -> None:
        """Process a single guild's year rollover if the time has come."""
        epoch = cfg.epoch

        if epoch.paused:
            logger.info(f'[{cfg!s}] Skipping task - time paused')
            return

        elapsed_days, year = get_year_status(cfg.id)

        if elapsed_days % epoch.length != 0:
            logger.info(f'[{cfg!s}] Year {year + 1} PC: {epoch.length - (elapsed_days % epoch.length)} days away')
            return

        latest_year = await Year.get_latest(cfg.id)

        if latest_year and year <= latest_year.year:
            logger.error(f'[{cfg!s}] Already advanced to year {latest_year.year}; was event manually triggered?')
            return

        logger.info(f'[{cfg!s}] Processing guild event')
        await self._advance_year(cfg, year)

    @webhook_logging(scope=logger)
    async def _advance_year(self, cfg: GuildConfig, year: int) -> None:
        """Execute the year advance for a guild."""
        logger.info(f'[{cfg!s}] Happy New Year! Advancing to Year {year} PC')
        guild = bot.get_guild(cfg.id)

        # --- Year Record Lifecycle ---
        now = int(datetime.now().astimezone().timestamp())

        if year > 1:
            await Year.finalize(cfg.id, year - 1, end_time=now)

        await Year.create_from_rollover(cfg.id, year, start_time=now)

        # --- Lore Channel Year Markers ---
        year_str = format_year_line(year)
        message_links = []

        for channel_id in cfg.channels.lore_channels:
            channel = guild.get_channel_or_thread(channel_id)
            message = await channel.send(year_str)

            await YearMarker.mark(year, message.id, channel=channel_id, guild=cfg.id)
            message_links.append(message.jump_url)

        # --- Increase Year VC ---
        year_vc = guild.get_channel_or_thread(cfg.channels.year_vc)
        await year_vc.edit(name=f'Current Year: {year} PC')

        # --- Edit Wiki ---
        wiki = get_wiki()
        await wiki.authenticate(config.wiki.user, config.wiki.key)

        text = await wiki.pages.get(config.wiki.page)
        updated_page = re.sub(r'Current Year: [\d]+ PC', f'Current Year: {year} PC', text, flags=re.IGNORECASE)

        await wiki.pages.edit(config.wiki.page, updated_page, f'Bumped to Year {year} PC')

        # --- Make Announcement ---
        channel = guild.get_channel_or_thread(cfg.channels.announcements)
        await channel.send(f'<@&{cfg.roles.announcements}> Year {year} PC. (weap)')

        # queue year links update
        from attubot.tasks import scheduler

        scheduler.add_job(job_construct_year_links(cfg.id), f'NovaYearEvent[{cfg!s}]')


# singleton instance for registration
nova_year_task = NovaYearTask()
