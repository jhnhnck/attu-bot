"""
AttuBot - Marker Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import Permissions
from discord.ext import commands
from discord.utils import snowflake_time

from attubot.config import Config
from attubot.logging import get_logger
from attubot.markers import YearMarker
from attubot.util import format_message_link, get_year_status, is_authorized_guild

logger = get_logger(__name__)

# --- Marker Commands ---

marker_group = discord.SlashCommandGroup('marker', description='Utlities related to managing year markers')

@marker_group.command(name='save', guilds_only=True, default_member_permissions=Permissions.all(), description='Updates marker to point to a different message (Admin only)')
@discord.commands.option(name='year', required=True, description='Year Number', input_type=int, min_value=1)
@discord.commands.option(name='link', required=True, description='Message Link', input_type=str)
@discord.commands.option(name='force', required=False, description='Override Mode', input_type=bool, default=False)
@commands.check(is_authorized_guild)
async def marker_save(ctx, year: int, link: str, force: bool):
    _, current_year = get_year_status()

    if year < 1 or year >= current_year:
        await ctx.respond(f'Failed: Only years 1 PC through {current_year} PC are valid options', ephemeral=True)
        return

    if 'discord.com/channels' not in link:
        await ctx.respond('Failed: Not a valid Discord message link', ephemeral=True)
        return

    # unpack url
    ids = link.split('/')[-3:]
    channel, message = int(ids[1]), int(ids[2])

    if channel not in Config.lore_channels and channel != Config.meta_chat_channel:
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
    await ctx.respond(f'{verb} marker for Year {year} PC as {format_message_link(Config.attu_guild, marker.channel, marker.message)}')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(marker_group)
