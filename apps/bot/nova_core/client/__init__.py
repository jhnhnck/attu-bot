# SPDX-License-Identifier: Apache-2.0
"""nova_core.client | discord client entry point."""

import importlib
import logging
import pkgutil
import shutil
import sys
from typing import cast

import discord
import structlog
from discord import ApplicationCommand, ApplicationContext

import nova_core.commands
from nova_core.client.core import bot, config, db  # noqa: F401 - re-exported as client API
from nova_core.client.embeds import ui_emoji


logger = structlog.stdlib.get_logger(__name__)


# --- Pycord Bridge Handler ---


class PycordBridgeHandler(logging.Handler):
    """marker handler kept for compatibility; routing happens via the dual root handlers in attu_logging.

    pycord's `discord.http` logger gets this attached in _setup_discord_logging() so the
    bridge symbol stays addressable for tests; records still propagate to the root handlers
    (stdout < WARNING, stderr >= WARNING) via the standard stdlib propagation chain.
    """

    def emit(self, record: logging.LogRecord) -> None:
        pass


logger.info('initializing')


# --- Commands ---


@discord.slash_command(name='ping', description='Simple command to test if the bot is online')
async def command_ping(ctx: ApplicationContext):
    latency_ms = round(ctx.bot.latency * 1000)
    await ctx.respond(f'Pong! ({latency_ms}ms) {ui_emoji("rockball")}')


# --- Extensions ---

# auto-discovered from nova_core/commands/; sorted for deterministic loading order
extensions_list = sorted(f'nova_core.commands.{mod.name}' for mod in pkgutil.iter_modules(nova_core.commands.__path__))


# --- Startup Helpers ---


def _check_deps():
    """check required system dependencies; raises Exception if any are missing"""
    for cmd in ('resvg', 'mongodump'):
        where = shutil.which(cmd)
        if where is None:
            raise Exception(f'missing dependency: {cmd}')
        logger.info(f'found dependency: {where}')


def _setup_discord_logging():
    """route pycord rate-limit logs through the structlog console renderer.

    structlog's root handlers (stdout < WARNING, stderr >= WARNING) handle rendering;
    PycordBridgeHandler is a marker so the existing test surface keeps working, and the
    bucket-resolution logic now lives as a foreign_pre_chain processor in attu_logging.
    """
    import logging as _logging
    from os import environ

    discord_http_logger = _logging.getLogger('discord.http')
    discord_http_logger.addHandler(PycordBridgeHandler())
    # WARNING by default keeps rate-limit warnings visible while suppressing per-request DEBUG noise;
    # DEBUG=1 opts back into the verbose http traces
    discord_http_logger.setLevel(_logging.DEBUG if 'DEBUG' in environ else _logging.WARNING)


def _load_event_handlers():
    """import event handler modules to register all bot event handlers"""
    importlib.import_module('nova_core.client.events')
    importlib.import_module('nova_core.client.modlog')


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
    logger.info('starting bot')
    _setup_discord_logging()
    config.on_init()
    _check_deps()
    _load_event_handlers()
    _register_core_commands()
    try:
        _load_extensions()
    except Exception as e:
        logger.critical(f'failed to load extensions, cannot start bot: {e}')
        sys.exit(1)
        return  # defensive; stops execution when sys.exit is mocked in tests
    logger.info('starting bot')
    bot.run(config.bot_token)
