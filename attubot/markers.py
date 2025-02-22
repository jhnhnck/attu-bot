"""
AttuBot - Locate Year Markers for Database Storage
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from discord.utils import snowflake_time
from tortoise import Tortoise, fields, run_async
from tortoise.models import Model

from attubot.config import Config
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

    def __str__(self):
        return f'{self.channel}/{self.message}'

# --- Marker Utils ---

async def markers_count():
    return await YearMarker.filter(channel=0).count()

# Throws exception on invalid year
async def markers_get(year: int, date: bool = False):
    marker = await YearMarker.get(channel=0, year=year)

    if date:
        return snowflake_time(marker.message)
    else:
        return int(snowflake_time(marker.message).timestamp())

async def markers_add(year: int, timestamp: int, channel: int = 0):
    logger.info(f'Marker appended: new={timestamp}')
    await YearMarker.create(channel=channel, year=year, message=timestamp)

# --- Extension Def ---

async def _init_db():
    logger.info('- Starting databases')

    await Tortoise.init(db_url=f'sqlite://{Config.db_path}', modules={'models': [__name__]})
    await Tortoise.generate_schemas(safe=True)

    # load in the timestamps from the config if they don't exist to channel 0
    if not await YearMarker.exists(channel=0, year=1):
        logger.info('Copying timestamps into marker database')
        for year, timestamp in enumerate(Config.timestamps, start=1):
            await YearMarker.create(channel=0, message=timestamp, year=year)

    logger.info(f'- Loaded [{(await YearMarker.last()).id}] entries')

def setup(bot):
    logger.info(f'Registered: {__name__}')

    run_async(_init_db())
