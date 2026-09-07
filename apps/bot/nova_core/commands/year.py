# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.year | user commands."""

from datetime import datetime, timedelta
from typing import cast

import discord
import structlog
from discord import ApplicationContext, Bot, SlashCommandGroup, TextChannel
from discord.enums import ChannelType

from nova_core.client.calendar import get_year_span, get_year_status
from nova_core.client.core import config
from nova_core.client.markers import resolve_marker
from nova_core.client.util import format_message_link
from nova_core.client.years import Year


logger = structlog.stdlib.get_logger(__name__)

# --- Year Commands ---

year_group = SlashCommandGroup('year', description='Utilities related to current, past or future years')


@year_group.command(name='check', description='Prints out information related to a specified year; if not specified, year defaults to the next year')
@discord.commands.option(name='year', required=False, description='Year Number', input_type=int, min_value=1)
async def year_check(ctx: ApplicationContext, year: int):
    guild_config = config.guild(ctx.guild.id)
    elapsed_days, current_year = get_year_status(guild=guild_config.id)
    year = year if year is not None else (current_year + 1)

    if year <= 0:
        await ctx.respond('Failed: only years 1 PC or later are valid options', ephemeral=True)

    elif year < current_year:
        year_record = await Year.get(guild_config.id, year)
        if year_record:
            await ctx.respond(f'Year {year} PC lasted for {year_record.duration} days, starting on <t:{year_record.start_time}:d> and ending on <t:{year_record.end_time}:d>')
        else:
            # fallback to computed span if no record exists
            year_span = await get_year_span(year, guild=guild_config.id)
            await ctx.respond(f'Year {year} PC lasted for {year_span.duration} days, starting on <t:{year_span.start_time}:d> and ending on <t:{year_span.end_time}:d>')

    elif guild_config.epoch.paused:
        await ctx.respond('Sorry! New Years is cancelled until further notice')

    elif year == current_year:
        year_span = await get_year_span(year, guild=guild_config.id)
        await ctx.respond(f'Year {year} PC will last for {year_span.duration} days, which started on <t:{year_span.start_time}:d> and will end on <t:{year_span.end_time}:d>')

    elif year == (current_year + 1):
        year_span = await get_year_span(year, guild=guild_config.id)
        if (elapsed_days % guild_config.epoch.length) == 0 and datetime.now().time() < guild_config.epoch.get_rollover_time():
            await ctx.respond(f'Happy New Year! Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

        else:
            await ctx.respond(f'Advancing to Year {current_year + 1} PC <t:{year_span.start_time}:R>')

    # easter egg (far future)
    elif (guild_config.epoch.length * (year - current_year - 1)) > (365 * 80):
        await ctx.respond(f"Year {year} PC won't matter because we'll all be dead; try something sooner maybe")

    else:
        year_span = await get_year_span(year, guild=guild_config.id)
        await ctx.respond(f'Year {year} PC will start on <t:{year_span.start_time}:d>')


@year_group.command(name='search', description='Prints search query for timlining')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
async def year_search(ctx: ApplicationContext, year: int):
    guild_config = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild_config.id)
    year_span = await get_year_span(year, guild=guild_config.id)
    msg = []

    if year <= 0:
        await ctx.respond('Failed: only years 1 PC or later are valid options', ephemeral=True)
        return

    if (guild_config.epoch.length * (year - current_year - 1)) > (365 * 10):
        await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', "the only constant in the universe: the timeline isn't caught up that far"))
        return

    canon_channels = [*guild_config.channels.lore_channels, guild_config.channels.meta_chat, *guild_config.channels.canon_channels]

    for channel_id in canon_channels:
        msg.append(f'in:{ctx.guild.get_channel(channel_id).name}')

    if year_span.start_time > 0:
        start = datetime.fromtimestamp(year_span.start_time, tz=config.timezone) - timedelta(days=1)
        msg.append(f'after:{start.strftime("%Y-%m-%d")}')

    if year_span.end_time > 0:
        end = datetime.fromtimestamp(year_span.end_time, tz=config.timezone) + timedelta(days=1)
        msg.append(f'before:{end.strftime("%Y-%m-%d")}')

    await ctx.respond(f'Year {year} PC: (paste in search bar)\n```\nMSG\n```\n'.replace('MSG', ' '.join(msg)))


async def find_marker_link(year: int, channel: TextChannel) -> str:
    """resolve and format the jump link to the year marker in a channel."""
    cfg = config.guild(channel.guild.id)
    marker = await resolve_marker(guild=cfg.id, channel=channel.id, year=year)

    logger.debug(f'resolved marker: year={year} channel=#{channel.name} source={marker.source} exact={marker.exact} message={marker.message}')

    return format_message_link(
        guild=cfg.id,
        channel=channel.id,
        message=marker.message,
        relative=(not marker.exact),
    )


@year_group.command(name='link', description='Links to the specified year in a lore channel; if not specified, channel defaults to #lore-news')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=False, description='Lore Channel', input_type=TextChannel)
async def year_link(ctx: ApplicationContext, year: int, channel: TextChannel | None):
    cfg = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=cfg.id)

    canon_channels = [*cfg.channels.lore_channels, cfg.channels.meta_chat, *cfg.channels.canon_channels]

    if channel is None:
        channel = cast('TextChannel', ctx.guild.get_channel_or_thread(canon_channels[0]))

    if year < 1 or year > current_year:
        await ctx.respond(f'Failed: only years 1 PC through {current_year} PC are valid options', ephemeral=True)

    # skip if its a not a text channel (so we can be unspecific about canon_channels)
    elif channel.type not in (ChannelType.text, ChannelType.news):
        await ctx.respond(f'Failed: command does not work on whatever {channel.mention} is', ephemeral=True)

    elif channel.id not in canon_channels:
        await ctx.respond('Failed: this command only works on lore channels', ephemeral=True)

    else:
        link = await find_marker_link(year, channel)
        await ctx.respond(f'{year} PC: {link}')


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(year_group)
