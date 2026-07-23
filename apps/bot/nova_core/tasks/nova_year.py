# SPDX-License-Identifier: Apache-2.0
"""nova_core.tasks.nova_year | guild year rollover task."""

import re
from datetime import datetime

from nova_core.client.calendar import format_year_line, get_next_year, get_year_status
from nova_core.client.core import bot, config
from nova_core.client.embeds import ui_emoji
from nova_core.client.util import webhook_logging
from nova_core.client.years import Year
from nova_core.config import GuildConfig
from nova_core.logging import get_logger
from nova_core.tasks.base import BaseTask
from nova_core.wiki import get_wiki


logger = get_logger(__name__)


async def job_construct_year_links(guild_id: int):
    from typing import cast

    from discord import ChannelType, TextChannel

    from nova_core.client.calendar import format_year_line, get_year_span
    from nova_core.client.core import bot, config
    from nova_core.client.years import Year
    from nova_core.commands.year import find_marker_link

    cfg = config.guild(guild_id)
    guild = bot.get_guild(cfg.id)
    lore_channels: list[TextChannel] = []

    all_years = await Year.all_for_guild(guild_id)
    current_year = all_years[-1].year if all_years else 1

    # collecting these so we're not constantly querying them later
    for channel_id in cfg.channels.lore_channels:
        channel = guild.get_channel_or_thread(channel_id)

        if channel is not None and channel.type == ChannelType.text:
            lore_channels.append(cast(TextChannel, channel))

    async def generate_links_block(year: int) -> str:
        year_str = format_year_line(year, level=2)
        marker_links = []

        for channel in lore_channels:
            jump_url = await find_marker_link(year, channel)
            marker_links.append(jump_url)

        span = await get_year_span(year, guild_id)

        return f'{year_str}\n<t:{span.start_time}:f> - <t:{span.end_time}:f>\n{"\n".join(marker_links)}'

    thread = guild.get_channel_or_thread(cfg.channels.year_links)

    if thread is None:
        logger.error(f'could not find channel {cfg.channels.year_links} for construction')
        return

    year_idx = 1
    async for message in thread.history(limit=None, oldest_first=True):
        if message.author.id != bot.user.id:
            await message.add_reaction(ui_emoji('rockball'))
            continue

        block = await generate_links_block(year_idx)

        if message.content != block:
            logger.warn(f'index {year_idx} is wrong for {message.jump_url}; replacing block')
            await message.edit(content=block)

        year_idx += 1

    while year_idx <= current_year:
        logger.warn(f'index {year_idx} is missing; sending new block')
        block = await generate_links_block(year_idx)
        await thread.send(content=block)
        year_idx += 1


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
            # all guilds are paused; check again in 30 minutes
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
            logger.info(f'[{cfg!s}] skipping task; time paused')
            return

        elapsed_days, year = get_year_status(cfg.id)

        if elapsed_days % epoch.length != 0:
            logger.info(f'[{cfg!s}] year {year + 1} PC: {epoch.length - (elapsed_days % epoch.length)} days away')
            return

        latest_year = await Year.get_latest(cfg.id)

        if latest_year and year <= latest_year.year:
            logger.error(f'[{cfg!s}] already advanced to year {latest_year.year} PC; was event manually triggered?')
            return

        logger.info(f'[{cfg!s}] processing guild event')
        await self._advance_year(cfg, year)

    @webhook_logging(scope=logger)
    async def _advance_year(self, cfg: GuildConfig, year: int) -> None:
        """Execute the year advance for a guild."""
        logger.info(f'[{cfg!s}] advancing to year {year} PC')
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
        from nova_core.tasks import scheduler

        scheduler.add_job(job_construct_year_links(cfg.id), 'NovaYearEvent', cfg)


# singleton instance for registration
nova_year_task = NovaYearTask()
