"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import sys
from pathlib import Path
from random import randrange
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Intents, Message
from discord.errors import CheckFailure
from discord.ext.commands import MissingPermissions
from tortoise import Tortoise

from attubot.config import NovaConfig, UnauthorizedGuild
from attubot.logging import get_logger
from attubot.util import create_task

# --- Initialization ---

logger = get_logger(__name__)
logger.info('Initializing...')

intents = Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- Error Handling ---

@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    logger.error(f'Error sent to `on_application_command_error()` from `{ctx.command.name}` error={error!s}')

    if isinstance(error, CheckFailure | UnauthorizedGuild):
        if ctx.guild.id in NovaConfig.authorized_guilds:
            await ctx.respond("You're not my real dad!")
        else:
            # catch all for if bot gets added to another discord guild
            await ctx.respond('This feature requires DoomBot(tm) Premium')

    elif isinstance(error, MissingPermissions):
        await ctx.respond('Nice try! <:rockball:1308981475114225694>')

    else:
        if ctx.command.name != 'force_error':
            await ctx.respond('An unexpected error occurred! <:rockball_player:1308977543034048552>')

        if hasattr(ctx.response, 'jump_url'):
            link = ctx.response.jump_url
        elif hasattr(ctx.channel, 'jump_url'):
            link = ctx.channel.jump_url
        elif hasattr(ctx.guild, 'jump_url'):
            link = ctx.guild.jump_url
        else:
            link = '`fuck idk man`'

        await logger.send_to_webhook(error, location=f'triggered by `{ctx.user.global_name}` at {link}')

    # Close any hung connections
    await Tortoise.close_connections()

# --- Events ---

@bot.event
async def on_ready():
    perms = '292595117136'

    if not hasattr(on_ready, 'has_run'):
        on_ready.has_run = False

    if not on_ready.has_run:
        on_ready.has_run = True

        logger.info(f'Logged in as {bot.user} (ID: {bot.user.id})!')
        logger.info(f'Add to a server:\n\thttps://discord.com/oauth2/authorize?client_id={bot.application_id}&scope=bot&permissions={perms}')

        try:
            await NovaConfig.on_ready(bot)

            # util depends on config being init, can't import later
            from attubot.tasks import error_hook_refresh
            await error_hook_refresh(bot)

            if NovaConfig.test_mode:
                logger.fatal('Reached ready state')
                raise Exception('(Test Mode)')

        except Exception as err:
            logger.fatal('Exception caught in on_ready() event; exiting', err)

            if str(err) != '(Test Mode)':
                await logger.send_to_webhook(err)

            await asyncio.gather(Tortoise.close_connections(), bot.close())
            sys.exit(1)

        logger.info('Pushing commands to Discord')
        await bot.sync_commands()

    else:
        logger.info(f'Reconnected as {bot.user} (ID: {bot.user.id})!')


@bot.event
async def on_message(message: Message):
    if message.guild is None:
        logger.debug(f'Skipping checks for message from "{message.author.name}" with blank guild')
        return

    if message.guild.id not in NovaConfig.valid_guilds:
        logger.debug(f'Skipping checks for message from "{message.author.name}" in "{message.guild.name}" (invalidated guild)')
        return

    channel = NovaConfig.guild(message.guild.id).channels.activity

    if message.channel.id == channel and message.content.startswith(f'[{NovaConfig.wiki.user.split("@")[0]}]'):  # TODO: verify correct part of wiki bot username
        if 'blocked' in message.content or 'registered' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')


@bot.before_invoke
async def on_application_command(ctx: ApplicationContext):
    logger.info(f'Command executed: user="{ctx.user.global_name}" command="/{ctx.command}" channel="{ctx.channel.name}" data={ctx.interaction.data}')


@bot.event
async def on_application_command_completion(ctx: ApplicationContext):
    await Tortoise.close_connections()


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    await ctx.respond('Pong! <:rockball:1308981475114225694>')


@discord.slash_command(name='pong', description='Another simple command to test if the bot is online')
async def command_pong(ctx: ApplicationContext):
    async def wait_random():
        sleep_time = 5 * randrange(25, 240)

        logger.info(f'Pong task sleeping for {sleep_time} seconds')
        await asyncio.sleep(sleep_time)

        await ctx.channel.send(f'{ctx.author.mention}! <:rockball:1308981475114225694>')

    if NovaConfig.is_owner(ctx.author.id):
        await ctx.respond(f'{ctx.author.mention}! <:rockball:1308981475114225694>')

    else:
        await ctx.respond('Ping! <:rockball:1308981475114225694>')
        create_task(wait_random())

# --- Trigger Function ---

def start_bot_loop():
    NovaConfig.on_init()

    def dep_check(path: str):
        dep = Path(path)

        if not dep.exists() and dep.is_file():
            raise Exception(f'missing dependency: {path}')

    logger.info('Checking Dependencies')
    dep_check('/usr/local/bin/resvg')

    logger.info('Loading Commands')
    bot.add_application_command(cast(ApplicationCommand, command_ping))
    bot.add_application_command(cast(ApplicationCommand, command_pong))

    logger.info('Loading Extensions')
    bot.load_extension('attubot.markers')  # db init step
    bot.load_extension('attubot.tasks')
    bot.load_extension('attubot.commands.config')
    bot.load_extension('attubot.commands.debug')
    bot.load_extension('attubot.commands.marker')
    bot.load_extension('attubot.commands.query')
    bot.load_extension('attubot.commands.time')
    bot.load_extension('attubot.commands.wiki')
    bot.load_extension('attubot.commands.year')

    logger.info('Starting Bot')
    bot.run(NovaConfig.bot_token)
