"""
AttuBot - Init and definitions file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import importlib
import shutil
import sys
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Intents

from attubot.config import NovaConfig
from attubot.database import MongoStorage
from attubot.logging import get_logger


logger = get_logger(__name__)
logger.info('Initializing...')

# create bot instance
logger.debug('Creating bot instance')
intents = Intents.default()
intents.message_content = True
intents.members = True
intents.emojis_and_stickers = True
intents.moderation = True

bot = discord.Bot(intents=intents)

# create config instance
logger.debug('Creating config instance')
config = NovaConfig()

# create database instance
logger.debug('Creating database instance')
db: MongoStorage = MongoStorage()


# --- Commands ---


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    await ctx.respond('Pong! <:rockball:1308981475114225694>')


# --- Startup Helpers ---

# extensions loaded by start_bot_loop; ordered list for deterministic loading
_EXTENSIONS = [
    'attubot.commands.debug',
    'attubot.commands.fix',
    'attubot.commands.marker',
    'attubot.commands.query',
    'attubot.commands.stars',
    'attubot.commands.time',
    'attubot.commands.wiki',
    'attubot.commands.year',
]


def _check_deps():
    """check required system dependencies; raises Exception if any are missing"""
    for cmd in ('resvg', 'mongodump'):
        where = shutil.which(cmd)
        if where is None:
            raise Exception(f'missing dependency: {cmd}')
        logger.info(f'found dependency: {where}')


def _load_event_handlers():
    """import events module to register all bot event handlers"""
    importlib.import_module('attubot.events')


def _register_core_commands():
    """register top-level slash commands that are not part of any extension"""
    logger.info('Loading Commands')
    bot.add_application_command(cast(ApplicationCommand, command_ping))


def _load_extensions():
    """load all slash command extensions in order; raises Exception on first failure"""
    logger.info('Loading Extensions')
    for ext in _EXTENSIONS:
        bot.load_extension(ext)


# --- Bot Entry Point ---


def start_bot_loop():
    logger.info('Starting DoomBot!')
    config.on_init()
    _check_deps()
    _load_event_handlers()
    _register_core_commands()
    try:
        _load_extensions()
    except Exception as e:
        logger.fatal(f'Failed to load extensions, cannot start bot: {e}')
        sys.exit(1)
        return  # defensive; stops execution when sys.exit is mocked in tests
    logger.info('Starting Bot')
    bot.run(config.bot_token)


# --- Web Entry Point ---


def start_bot_loop_web():
    """alias for web process use; not intended to be called directly"""
    from attubot.web.app import start_web

    start_web()
