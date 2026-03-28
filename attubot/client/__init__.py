"""
AttuBot - Discord Client Entry Point
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import importlib
import pkgutil
import shutil
import sys
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext

import attubot.commands
from attubot.client.core import bot, config, db  # noqa: F401 - re-exported as client API
from attubot.logging import get_logger


logger = get_logger(__name__)
logger.info('initializing')


# --- Commands ---


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    await ctx.respond('Pong! <:rockball:1308981475114225694>')


# --- Extensions ---

# auto-discovered from attubot/commands/; sorted for deterministic loading order
extensions_list = sorted(f'attubot.commands.{mod.name}' for mod in pkgutil.iter_modules(attubot.commands.__path__))


# --- Startup Helpers ---


def _check_deps():
    """check required system dependencies; raises Exception if any are missing"""
    for cmd in ('resvg', 'mongodump'):
        where = shutil.which(cmd)
        if where is None:
            raise Exception(f'missing dependency: {cmd}')
        logger.info(f'found dependency: {where}')


def _load_event_handlers():
    """import event handler modules to register all bot event handlers"""
    importlib.import_module('attubot.client.events')
    importlib.import_module('attubot.client.modlog')


def _register_core_commands():
    """register top-level slash commands that are not part of any extension"""
    logger.info('loading commands')
    bot.add_application_command(cast(ApplicationCommand, command_ping))


def _load_extensions():
    """load all slash command extensions in order; raises Exception on first failure"""
    logger.info('loading extensions')
    for ext in extensions_list:
        bot.load_extension(ext)


# --- Bot Entry Point ---


def start_bot_loop():
    logger.info('starting doombot')
    config.on_init()
    _check_deps()
    _load_event_handlers()
    _register_core_commands()
    try:
        _load_extensions()
    except Exception as e:
        logger.fatal(f'failed to load extensions, cannot start bot: {e}')
        sys.exit(1)
        return  # defensive; stops execution when sys.exit is mocked in tests
    logger.info('starting bot')
    bot.run(config.bot_token)


# --- Web Entry Point ---


def start_bot_loop_web():
    """alias for web process use; not intended to be called directly"""
    from attubot.web.app import start_web

    start_web()
