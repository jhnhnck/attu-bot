"""
AttuBot - Marker Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import ApplicationContext, Bot, Permissions, SlashCommandGroup
from discord.ext import commands
from discord.utils import snowflake_time

from attubot.calendar import get_year_status
from attubot.config import NovaConfig
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import format_message_link, is_authorized_guild

logger = get_logger(__name__)

# --- Marker Commands ---

marker_group = SlashCommandGroup('marker', default_member_permissions=Permissions.all(), description='Utilities related to managing year markers (Admin Only)')

@marker_group.command(name='save', description='Updates marker to point to a different message')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='link', required=True, description='Message Link', input_type=str)
@discord.commands.option(name='force', required=False, description='Override Mode', input_type=bool, default=False)
@commands.check(is_authorized_guild)
async def marker_save(ctx: ApplicationContext, year: int, link: str, force: bool):
    guild_config = NovaConfig.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=guild_config.id)

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    if 'discord.com/channels' not in link:
        await ctx.respond('Failed: Not a valid Discord message link', ephemeral=True)
        return

    # unpack url
    ids = link.split('/')[-3:]
    channel, message = int(ids[1]), int(ids[2])

    if channel not in guild_config.channels.lore_channels:
        await ctx.respond('Failed: Channel is not a lore channel', ephemeral=True)
        return

    # Check if close
    est_marker = await YearMarker.get(year=year, channel=0)
    time_diff = abs((snowflake_time(est_marker.message) - snowflake_time(message)).total_seconds())

    if time_diff > 600 and not force:
        await ctx.respond(f'Failed: Provided link is {int(time_diff)} seconds off from expected; if correct, override with `force:true`', ephemeral=True)
        return

    # Add or update marker
    marker, created = await YearMarker.get_or_create(year=year, channel=channel, defaults={'message': message})
    marker.message = message
    marker.exact = True
    await marker.save()

    verb = 'Created' if created else 'Updated'
    await ctx.respond(f'{verb} marker for Year {year} PC as {format_message_link(guild_config.id, marker.channel, marker.message)}')


@marker_group.command(name='set', description='Sets marker timestamp for when a specifc year starts')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='snowflake', required=True, description='Message ID', input_type=int)
@commands.check(is_authorized_guild)
async def marker_set(ctx: ApplicationContext, year: int, snowflake: int):
    guild_config = NovaConfig.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=guild_config.id)
    snowflake = int(snowflake)

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    # Check if close
    est_marker = await YearMarker.get(year=year, channel=0)
    old_time = int(snowflake_time(est_marker.message).timestamp())
    new_time = int(snowflake_time(snowflake).timestamp())

    # Log change
    logger.info(f'Moving {year} PC start from {est_marker.message} to {snowflake}')

    # Add or update marker
    est_marker.message = snowflake
    await est_marker.save()

    await ctx.respond(f'Adjusted {year} PC start from <t:{old_time}:d> to <t:{new_time}:d>')


@marker_group.command(name='clear', description='Removes marker for a specific channel and year')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='channel', required=True, description='Lore Channel', input_type=discord.TextChannel)
@commands.check(is_authorized_guild)
async def marker_clear(ctx: ApplicationContext, year: int, channel: discord.TextChannel):
    guild_config = NovaConfig.guild(ctx.guild.id)
    _, current_year = get_year_status(guild=guild_config.id)

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    if channel.id not in guild_config.channels.lore_channels:
        await ctx.respond('Failed: Channel is not a lore channel', ephemeral=True)
        return

    marker = await YearMarker.get_or_none(year=year, channel=channel.id)

    if marker is not None:
        await marker.delete()
        await ctx.respond(f'Cleared saved marker for {year} PC in <#{channel.id}>')

    else:
        await ctx.respond('Failed: Could not clear marker as it did not exist', ephemeral=True)

# --- Extension Def ---

def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(marker_group)
