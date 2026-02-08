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

from attubot import config
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

    @classmethod
    async def total(cls, guild: int | None = None) -> int:
        if guild is None:
            guild = config.primary_guild

        return await cls.filter(channel=guild).count()

    @classmethod  # Throws exception on invalid year
    async def timestamp(cls, year: int, guild: int | None = None) -> int:
        if guild is None:
            guild = config.primary_guild

        marker = await cls.get(channel=guild, year=year)
        return int(snowflake_time(marker.message).timestamp())

    @classmethod
    async def mark(cls, year: int, timestamp: int, channel: int | None = None):
        if channel is None:
            channel = config.primary_guild

        logger.info(f'Marker appended: channel={channel} new={timestamp}')
        await cls.create(channel=channel, year=year, message=timestamp)

# --- Extension Def ---

async def _init_db():
    logger.info('Connecting to database')

    await Tortoise.init(db_url=f'sqlite://{config.db_path}', modules={'models': [__name__, 'attubot.config']})
    await Tortoise.generate_schemas(safe=True)

    logger.info(f'Loaded [{await YearMarker.all().count()}] markers')

    logger.info('Unpacking additional config values from database')
    await config.on_load()


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(_init_db())

