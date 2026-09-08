# SPDX-License-Identifier: Apache-2.0
"""nova_core.commands.marker | marker commands."""

import discord
import structlog
from discord import ApplicationContext, Bot, Permissions, SlashCommandGroup
from discord.ext import commands
from discord.utils import snowflake_time

from nova_core.client.calendar import get_year_status
from nova_core.client.core import config
from nova_core.client.markers import YearMarker
from nova_core.client.util import format_message_link, is_authorized_guild
from nova_core.config import UnauthorizedGuild


logger = structlog.stdlib.get_logger(__name__)

# --- Marker Commands ---

marker_group = SlashCommandGroup('marker', default_member_permissions=Permissions.all(), description='manage year markers (admin only)')


@marker_group.command(name='save', description="point a year's marker at a different message")
@discord.commands.option(name='year', required=True, description='which year to move the marker to (1 to current)', input_type=int, min_value=1)
@discord.commands.option(name='link', required=True, description='the message the marker should point at (full discord link)', input_type=str)
@discord.commands.option(name='force', required=False, description='accept a link far from the expected time', input_type=bool, default=False)
@commands.check(is_authorized_guild)
async def marker_save(ctx: ApplicationContext, year: int, link: str, force: bool):
    if 'discord.com/channels' not in link:
        await ctx.respond('that does not look like a discord message link', ephemeral=True)
        return

    ids = link.split('/')[-3:]
    guild, channel, message = int(ids[0]), int(ids[1]), int(ids[2])

    try:
        guild_config = config.guild(guild)
        _, current_year = get_year_status(guild=guild_config.id)

    except UnauthorizedGuild:
        await ctx.respond("this server isn't set up for me", ephemeral=True)
        return

    if year < 1 or year >= current_year:
        await ctx.respond(f'only years 1 PC through {current_year} PC exist', ephemeral=True)
        return

    if channel not in guild_config.channels.lore_channels:
        await ctx.respond("that isn't a lore channel", ephemeral=True)
        return

    est_marker = await YearMarker.get(channel=channel, year=year)
    time_diff = abs((snowflake_time(est_marker.message) - snowflake_time(message)).total_seconds())

    if time_diff > 600 and not force:
        await ctx.respond(f'provided link is {int(time_diff)} seconds off from expected; if correct, override with `force:true`', ephemeral=True)
        return

    marker, created = await YearMarker.get_or_create(guild=guild, channel=channel, year=year, message=message)
    await marker.update(message=message, exact=True)

    verb = 'Created' if created else 'Updated'
    await ctx.respond(f'{verb} marker for {year} PC as {format_message_link(guild_config.id, marker.channel, marker.message)}')


@marker_group.command(name='set', description='set when a year starts, from a message id')
@discord.commands.option(name='year', required=True, description='which year to set the start of (1 or later)', input_type=int, min_value=1)
@discord.commands.option(name='snowflake', required=True, description='the message whose timestamp starts the year', input_type=int)
@commands.check(is_authorized_guild)
async def marker_set(ctx: ApplicationContext, year: int, snowflake: int):
    guild_config = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=guild_config.id)
    snowflake = int(snowflake)

    if year < 1 or year >= current_year:
        await ctx.respond(f'only years 1 PC through {current_year} PC exist', ephemeral=True)
        return

    est_marker = await YearMarker.get_any(guild=guild_config.id, year=year)
    old_time = int(snowflake_time(est_marker.message).timestamp())
    new_time = int(snowflake_time(snowflake).timestamp())

    logger.info(f'moving {year} PC start from {est_marker.message} to {snowflake}')
    await est_marker.update(message=snowflake)

    await ctx.respond(f'adjusted {year} PC start from <t:{old_time}:d> to <t:{new_time}:d>')


@marker_group.command(name='clear', description="remove a year's marker from a lore channel")
@discord.commands.option(name='year', required=True, description='which year to clear (1 or later)', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=True, description='which lore channel to clear it from', input_type=discord.TextChannel)
@commands.check(is_authorized_guild)
async def marker_clear(ctx: ApplicationContext, year: int, channel: discord.TextChannel):
    guild_config = config.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=guild_config.id)

    if year < 1 or year >= current_year:
        await ctx.respond(f'only years 1 PC through {current_year} PC exist', ephemeral=True)
        return

    if channel.id not in guild_config.channels.lore_channels:
        await ctx.respond("that isn't a lore channel", ephemeral=True)
        return

    marker = await YearMarker.get(channel=channel.id, year=year)

    if marker is not None:
        await marker.delete()
        await ctx.respond(f'cleared the marker for {year} PC in <#{channel.id}>')

    else:
        await ctx.respond(f"there's no marker for {year} PC in {channel.mention}", ephemeral=True)


# --- Extension Def ---


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    bot.add_application_command(marker_group)
