"""
AttuBot - Core Singleton Objects
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

# leaf module - imports only third-party and sibling sub-packages, never attubot itself
# this means any module can do `from attubot.client.core import bot, config, db` without circularity

import discord
from discord import Intents

from attubot.config import NovaConfig
from attubot.database import MongoStorage


intents = Intents.default()
intents.message_content = True
intents.members = True
intents.emojis_and_stickers = True
intents.moderation = True

bot = discord.Bot(intents=intents)
config = NovaConfig()
db: MongoStorage = MongoStorage()
