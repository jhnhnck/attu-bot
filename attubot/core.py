"""
AttuBot - Main file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
import traceback
from typing import cast

import aiohttp
import discord
from discord import ApplicationContext, Intents, Message, Webhook
from discord.errors import CheckFailure
from discord.ext.commands import MissingPermissions
from tortoise import Tortoise

from attubot.config import NovaConfig, UnauthorizedGuild
from attubot.logging import get_logger

# --- Initialization ---

logger = get_logger(__name__)
logger.info('Initializing...')

intents = Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# --- Error Handling ---

async def send_to_webhook(error: Exception):
    tb_str = ''.join(traceback.format_exception(error))

    logger.error(f'{error!s}\n{tb_str}')

    try:
        # this removes the useless bits
        tb_str = tb_str.split('The above exception')[0]
        msg = f'**{error}**\n```\n{tb_str}```'

        # trim to discord character length
        if len(msg) > 2000:
            msg = msg[:1992] + '\n...\n```'

        async with aiohttp.ClientSession() as session:
            webhook = Webhook.from_url(NovaConfig.error_hook, session=session)
            await webhook.send(msg, username='DoomBot')

    except Exception as err:
        logger.error(f'Issue logging error to configured webhook: {err}')


@bot.event
async def on_application_command_error(ctx: ApplicationContext, error: Exception):
    logger.error(f'Error sent to `on_application_command_error()` error={error!s}')

    if isinstance(error, CheckFailure | UnauthorizedGuild):
        if ctx.guild.id in NovaConfig.authorized_guilds:
            await ctx.respond("You're not my real dad!")
        else:
            # catch all for if bot gets added to another discord guild
            await ctx.respond('This feature requires DoomBot(tm) Premium')

    elif isinstance(error, MissingPermissions):
        await ctx.respond('Nice try! <:rockball:1308981475114225694>')

    else:
        await ctx.respond('An unexpected error occurred! <:rockball_player:1308977543034048552>')
        await send_to_webhook(error)

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

        except Exception as err:
            logger.fatal('Exception caused by config on_ready() event', err)
            await bot.close()
            sys.exit(0)

        if NovaConfig.test_mode:
            logger.fatal('Reached ready state; exiting...')
            await bot.close()
            sys.exit(0)

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
        if 'blocked' in message.content:
            await message.add_reaction('<:tieteran_wave:1308636215930654801>')
        else:
            await message.add_reaction('💖')


@bot.before_invoke
async def on_application_command(ctx: ApplicationContext):
    logger.info(f'Command executed: user={ctx.user.global_name} command={ctx.command} channel={ctx.channel.name} data={ctx.interaction.data}')


@bot.event
async def on_application_command_completion(ctx: ApplicationContext):
    await Tortoise.close_connections()


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    await ctx.respond('Pong! <:rockball:1308981475114225694>')

# --- Trigger Function ---

def start_bot_loop():
    NovaConfig.on_init()

    logger.info('Loading Commands')
    bot.add_application_command(cast(discord.ApplicationCommand, command_ping))

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
