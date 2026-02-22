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
from discord import ApplicationCommand, ApplicationContext, Message
from discord.errors import CheckFailure
from discord.ext.commands import MissingPermissions

from attubot import bot, config
from attubot.config import UnauthorizedGuild
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Error Handling ---


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    logger.error(f'Error sent to `on_application_command_error()` from `{ctx.command.name}` error={error!s}')

    if isinstance(error, CheckFailure | UnauthorizedGuild):
        if ctx.guild.id in config.authorized_guilds:
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


# --- Events ---


async def _shutdown(exit_code: int = 1):
    """close db connections and stop the event loop cleanly"""
    from attubot import db

    if db.client:
        await db.client.close()
    asyncio.get_running_loop().stop()
    sys.exit(exit_code)


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
            logger.info('Connecting to database and initializing repositories...')
            from attubot.database import init_database

            await init_database(config.database.url, config.database.name)

            logger.info('Loading configuration from database...')
            await config.on_load()
        except Exception as err:
            logger.fatal('Exception caught initializing database; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        try:
            await config.on_ready()
        except Exception as err:
            logger.fatal('Exception caught in on_ready() event; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        if config.test_mode:
            logger.fatal('Reached ready state')
            await _shutdown(exit_code=0)
            return

        # start task scheduler
        try:
            from attubot.tasks import scheduler

            await scheduler.start_all()
        except Exception as err:
            logger.fatal('Exception caught starting task scheduler; exiting', err)
            await logger.send_to_webhook(err)
            await _shutdown(exit_code=1)
            return

        logger.info('Pushing commands to Discord')
        await bot.sync_commands()

    else:
        logger.info(f'Reconnected as {bot.user} (ID: {bot.user.id})!')


@bot.event
async def on_message(message: Message):
    if message.guild is None:
        logger.debug(f'Skipping checks for message from "{message.author.name}" with blank guild')
        return

    if message.guild.id not in config.valid_guilds:
        logger.debug(f'Skipping checks for message from "{message.author.name}" in "{message.guild.name}" (invalidated guild)')
        return

    channel = config.guild(message.guild.id).channels.activity

    if message.channel.id == channel and message.content.startswith(f'[{config.wiki.user.split("@")[0]}]'):
        if 'blocked' in message.content or 'registered' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')


@bot.before_invoke
async def on_application_command(ctx: ApplicationContext):
    logger.info(f'Command executed: user="{ctx.user.global_name}" command="/{ctx.command}" channel="{ctx.channel.name}" data={ctx.interaction.data}')


# --- Commands ---


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

    if config.is_owner(ctx.author.id):
        await ctx.respond(f'{ctx.author.mention}! <:rockball:1308981475114225694>')

    else:
        await ctx.respond('Ping! <:rockball:1308981475114225694>')
        from attubot.tasks import scheduler

        scheduler.add_job(wait_random(), f'PongTask[{ctx.author.name}]')


@discord.slash_command(name='test', description='Simple command to test with')
async def command_test(ctx: ApplicationContext):
    """Utility command for debugging - kept unregistered for manual use when needed"""
    if not config.is_owner(ctx.author.id):
        await ctx.respond('Do I know you?', ephemeral=True)
        return

    try:
        pass

    except Exception as err:
        await logger.send_to_webhook(err)

        await ctx.respond('https://discord.com/channels/572148465870700544/1256800104082313257')
        return


# --- Trigger Function ---


def start_bot_loop():
    logger.info('Starting DoomBot!')
    config.on_init()

    def dep_check(path: str):
        dep = Path(path)

        if not dep.is_file():
            raise Exception(f'missing dependency: {path}')

    logger.info('Checking Dependencies')
    dep_check('/usr/local/bin/resvg')

    logger.info('Loading Commands')
    bot.add_application_command(cast(ApplicationCommand, command_ping))
    bot.add_application_command(cast(ApplicationCommand, command_pong))
    # bot.add_application_command(cast(ApplicationCommand, command_test))

    logger.info('Loading Extensions')
    try:
        bot.load_extension('attubot.commands.debug')
        bot.load_extension('attubot.commands.marker')
        bot.load_extension('attubot.commands.query')
        bot.load_extension('attubot.commands.time')
        bot.load_extension('attubot.commands.wiki')
        bot.load_extension('attubot.commands.year')
    except Exception as e:
        logger.fatal(f'Failed to load extensions, cannot start bot: {e}')
        sys.exit(1)

    logger.info('Starting Bot')
    bot.run(config.bot_token)
