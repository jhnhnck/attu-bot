"""
AttuBot - Init and definitions file
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

__title__ = 'AttuBot'
__author__ = 'jhnhnck'
__license__ = 'Apache License, Version 2.0'
__copyright__ = 'Copyright (c) 2026 John Hancock, The Attu Project'
__schema__ = '1.8.0'  # previously __version__
__email__ = 'doom@attuproject.org'
__description__ = 'A discord bot designed for automating tasks for the Attu Project'

# TODO use gitpython to mark if dirty
__version__ = '26.2.0'

import discord
from discord import Intents

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)
logger.info('Initializing...')

# Create bot instance
logger.debug('Creating bot instance')
intents = Intents.default()
intents.message_content = True

bot = discord.Bot(intents=intents)

# Create config instance
logger.debug('Creating config instance')
config = NovaConfig()
