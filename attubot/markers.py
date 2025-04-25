"""
AttuBot - Locate Year Markers for Database Storage
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from typing import override

from discord import Bot
from discord.utils import snowflake_time
from tortoise import Tortoise, fields
from tortoise.models import Model

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Database Model ---

class YearMarker(Model):
    id = fields.IntField(primary_key=True)
    channel = fields.IntField()
    message = fields.IntField()
    year = fields.IntField()
    exact = fields.BooleanField(default=False)
    wiki_page = fields.BooleanField(default=False)

    @override
    def __str__(self) -> str:
        return f'{self.channel}/{self.message}'

    @staticmethod
    async def total(guild: int | None = None) -> int:
        if guild is None:
            guild = NovaConfig.primary_guild

        return await YearMarker.filter(channel=guild).count()

    @staticmethod  # Throws exception on invalid year
    async def timestamp(year: int, guild: int | None = None) -> int:
        if guild is None:
            guild = NovaConfig.primary_guild

        marker = await YearMarker.get(channel=guild, year=year)
        return int(snowflake_time(marker.message).timestamp())

    @staticmethod
    async def mark(year: int, timestamp: int, channel: int | None = None):
        if channel is None:
            channel = NovaConfig.primary_guild

        logger.info(f'Marker appended: channel={channel} new={timestamp}')
        await YearMarker.create(channel=channel, year=year, message=timestamp)

# --- Extension Def ---

async def _init_db():
    logger.info('Connecting to database')

    await Tortoise.init(db_url=f'sqlite://{NovaConfig.db_path}', modules={'models': [__name__, 'attubot.config']})
    await Tortoise.generate_schemas(safe=True)

    logger.info(f'Loaded [{await YearMarker.all().count()}] markers')

    logger.info('Unpacking additional config values from database')
    await NovaConfig.on_load()


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_init_db())

