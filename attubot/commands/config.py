"""
AttuBot - Config Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import discord
from discord import Permissions

from attubot.config import NovaConfig, NovaToken
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Commands ---

config_group = discord.SlashCommandGroup('config', default_member_permissions=Permissions.all(), description='Modify various options for bot behavior (Admin only)')

@config_group.command(name='delete', description='Delete a specific key from the config table')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_delete(ctx, key: str):
    token_ref = NovaConfig.parse_key(key, guild=ctx.guild.id)

    # check if valid token key
    if token_ref is None:
        await ctx.respond('Failed: Key is not a valid identifier', ephemeral=True)
        return

    # check if authorized to view
    if not token_ref.authorized(ctx.author.id, ctx.guild.id, mode='write'):
        await ctx.respond('Failed: You do not have permission to access that identifier', ephemeral=True)
        return

    await NovaConfig.delete(token_ref.key, guild=token_ref.guild)
    await ctx.respond(f'Reset `{token_ref!s}` to the default value')


@config_group.command(name='get', description='Fetch the value of a configuration')
@discord.commands.option(name='key', required=True, description='Config identifier', input_type=str)
async def config_get(ctx, key: str):
    token_ref = NovaConfig.parse_key(key, guild=ctx.guild.id)

    # check if valid token key
    if token_ref is None:
        await ctx.respond('Failed: Key is not a valid identifier', ephemeral=True)
        return

    # check if authorized to view
    if not token_ref.authorized(ctx.author.id, ctx.guild.id, mode='read'):
        await ctx.respond('Failed: You do not have permission to access that identifier', ephemeral=True)
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
    token_ref = NovaConfig.parse_key(key, guild=ctx.guild.id)

    # check if valid token key
    if token_ref is None:
        await ctx.respond('Failed: Key is not a valid identifier', ephemeral=True)
        return

    # check if authorized to view
    if not token_ref.authorized(ctx.author.id, ctx.guild.id, mode='write'):
        await ctx.respond('Failed: You do not have permission to access that identifier', ephemeral=True)
        return

    token = await NovaConfig.get_raw(token_ref.key, guild=token_ref.guild)
    old_value = token.unpack()

    try:
        token.value = f'X = {value}'
        new_value = token.unpack()
        await token.save()

    except Exception as err:
        await ctx.respond(f"Failed: Couldn't parse value; {err!s}", ephemeral=True)
        await token.pack(old_value)  # restore old value on fail
        return

    if token_ref.guild == 0:
        await NovaConfig.load_globals()  # no type checking on this btw

    elif await NovaConfig.load_guild(token_ref.guild):
        await ctx.respond(f'Changed `{token_ref!s}` from `{old_value!s}` to `{new_value!s}`')

    else:
        await ctx.respond("Failed: Couldn't validate guild with new value", ephemeral=True)
        await token.pack(old_value)  # restore old value on fail


@config_group.command(name='show', description='Show the entire guild configuration')
async def config_show(ctx):
        config = {}
        msg = []

        async for token in NovaToken.filter(guild=ctx.guild.id):
            config[str(token.key)] = token.unpack()

        for key in NovaConfig.guild_keys:
            if key in config:
                msg.append(f'`{key}` = `{config[key]!s}`')
            else:
                msg.append(f'`{key}` = *unset / default*')

        await ctx.respond('Current Guild Config:\n' + '\n'.join(msg))


@config_group.command(name='validate', description='Check if the current configuration is valid')
async def config_validate(ctx):
    if ctx.guild.id in NovaConfig.valid_guilds:
        await ctx.respond('Guild Status: :ballot_box_with_check:')
    else:
        await ctx.respond('Guild Status: :no_entry:')

# --- Extension Def ---

def setup(bot):
    logger.info(f'Registered: {__name__}')

    bot.add_application_command(config_group)
