"""
AttuBot - Config Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import Permissions
from discord.ext import commands

from attubot.config import NovaConfig
from attubot.logging import get_logger
from attubot.util import is_bot_owner

logger = get_logger(__name__)

# --- Config Commands ---

config_group = discord.SlashCommandGroup('config', default_member_permissions=Permissions.all(), description='Modify various options for bot behavior (Admin only)')

@config_group.command(name='get', description='Fetch the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_get(ctx, key: str):
    await ctx.respond('Oops. Not Implemented!')

@config_group.command(name='set', description='Set the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
@discord.commands.option(name='value', required=True, description='TOML-formatted Value', input_type=str)
@commands.check(is_bot_owner)  # This is probably a security hole, so keeping it trusted only for now
async def config_set(ctx, key: str, value: str):
    await ctx.respond('Oops. Not Implemented!')

@config_group.command(name='show', description='Show the entire server configuration')
async def config_show(ctx):
    await ctx.respond('Oops. Not Implemented!')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(config_group)

