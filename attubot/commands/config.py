"""
AttuBot - Config Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import Permissions

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Commands ---

config_group = discord.SlashCommandGroup('config', default_member_permissions=Permissions.all(), description='Modify various options for bot behavior (Admin only)')

@config_group.command(name='delete', description='Delete a specific key from the config table')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_delete(ctx, key: str):
    await ctx.respond('Oops. Not Implemented!', ethemeral=True)


@config_group.command(name='get', description='Fetch the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_get(ctx, key: str):
    await ctx.respond('Oops. Not Implemented!', ethemeral=True)


@config_group.command(name='list', description='List out the available config options')
async def config_list(ctx):
    await ctx.respond('Available Options:\n' + ''.join([f'- {x}\n' for x in NovaConfig.guild_keys]))


@config_group.command(name='set', description='Set the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
@discord.commands.option(name='value', required=True, description='', input_type=str)
async def config_set(ctx, key: str, value: str):
    await ctx.respond('Oops. Not Implemented!', ephemeral=True)


@config_group.command(name='show', description='Show the entire server configuration')
async def config_show(ctx):
    await ctx.respond('Oops. Not Implemented!', ethemeral=True)

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(config_group)
