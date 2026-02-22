"""
AttuBot - Init and definitions file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

__title__ = 'AttuBot'
__author__ = 'jhnhnck'
__license__ = 'Apache License, Version 2.0'
__copyright__ = 'Copyright (c) 2026 John Hancock, The Attu Project'
__schema__ = '2.4.0'  # previously __version__
__email__ = 'doom@attuproject.org'
__description__ = 'A discord bot designed for automating tasks for the Attu Project'

__version__ = '26.2.19'
__build_time__ = 'Thu Aug 11 02:23:20 UTC 2022'  # stamped during docker build

import sys
from pathlib import Path
from typing import cast

import discord
from discord import ApplicationContext, ApplicationCommand, Intents

from attubot.config import NovaConfig
from attubot.database import MongoStorage
from attubot.logging import get_logger

logger = get_logger(__name__)
logger.info('Initializing...')

# Create bot instance
logger.debug('Creating bot instance')
intents = Intents.default()
intents.message_content = True
intents.members = True

bot = discord.Bot(intents=intents)

# Create config instance
logger.debug('Creating config instance')
config = NovaConfig()

# Create database instance
logger.debug('Creating database instance')
db: MongoStorage = MongoStorage()


# --- Commands ---


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    await ctx.respond('Pong! <:rockball:1308981475114225694>')


# --- Bot Entry Point ---


def start_bot_loop():
    logger.info('Starting DoomBot!')
    config.on_init()

    def dep_check(path: str):
        dep = Path(path)

        if not dep.is_file():
            raise Exception(f'missing dependency: {path}')

    logger.info('Checking Dependencies')
    dep_check('/usr/local/bin/resvg')

    # import events module to register all bot event handlers
    import attubot.events  # noqa: F401

    logger.info('Loading Commands')
    bot.add_application_command(cast(ApplicationCommand, command_ping))

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
