# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.core | core singleton objects."""

# leaf module - imports only third-party and sibling sub-packages, never nova_core itself
# this means any module can do `from nova_core.client.core import bot, config, db` without circularity

import discord
from discord import Intents

from nova_core.config import NovaConfig
from nova_core.database import MongoStorage


intents = Intents.default()
intents.message_content = True
intents.members = True
intents.emojis_and_stickers = True
intents.moderation = True

bot = discord.Bot(intents=intents)
config = NovaConfig()
db: MongoStorage = MongoStorage()
