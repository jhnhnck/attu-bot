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
    await ctx.respond('Oops. Not Implemented!', ephemeral=True)


@config_group.command(name='get', description='Fetch the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_get(ctx, key: str):
    token_ref = NovaConfig.parse_key(ctx.guild.id, key)

    # check if valid token key
    if token_ref is None:
        await ctx.respond('Failed: Key is not a valid identifier', ephemeral=True)
        return

    # check if authorized to view
    if not token_ref.authorized(ctx.author.id, ctx.guild.id, mode='read'):
        await ctx.respond('Failed: You have no permission to access that identifier', ephemeral=True)
        return

    value = await NovaConfig.get(token_ref.key, guild=token_ref.guild)

    await ctx.respond(f'`{token_ref!s}` = `{value!s}`')


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
    await ctx.respond('Oops. Not Implemented!', ephemeral=True)

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(config_group)
