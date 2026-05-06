# SPDX-License-Identifier: Apache-2.0
"""doom_bot.client.core | core singleton objects."""

# leaf module - imports only third-party and sibling sub-packages, never doom_bot itself
# this means any module can do `from doom_bot.client.core import bot, config, db` without circularity

import discord
from discord import Intents

from doom_bot.config import NovaConfig
from doom_bot.database import MongoStorage


intents = Intents.default()
intents.message_content = True
intents.members = True
intents.emojis_and_stickers = True
intents.moderation = True

bot = discord.Bot(intents=intents)
config = NovaConfig()
db: MongoStorage = MongoStorage()
