"""
AttuBot - Database Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.database.connection import MongoStorage
from attubot.database.models import (
    GuildConfigDocument,
    ReloadSignalDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)
from attubot.database.repositories import (
    ConfigRepository,
    ReloadSignalRepository,
    YearMarkerRepository,
    YearRepository,
)
from attubot.logging import get_logger

logger = get_logger(__name__)


async def init_database(url: str, name: str):
    """Connect to MongoDB and initialize all repository indexes.

    Args:
        url: MongoDB connection URL
        name: Database name
    """
    from attubot import config, db

    # connect first so all repos can get a db handle
    await db.connect(url, name)
    database = db.get_db()

    # config repo is needed before on_load() reads from the database
    config_repo = ConfigRepository(database)
    await config_repo.init_indexes()
    config.config_repo = config_repo
    logger.debug('config repo ready')

    marker_repo = YearMarkerRepository(database)
    year_repo = YearRepository(database)
    signal_repo = ReloadSignalRepository(database)

    await marker_repo.init_indexes()
    logger.debug('marker indexes ready')

    await year_repo.init_indexes()
    logger.debug('year indexes ready')

    await signal_repo.init_indexes()
    logger.debug('signal indexes ready')

    # seed module-level repo singletons so lazy _get_repo() calls work
    import attubot.markers as _markers
    import attubot.signals as _signals
    import attubot.years as _years

    _markers._marker_repo = marker_repo
    _years._year_repo = year_repo
    _signals._repo = signal_repo

    logger.info('database initialized')


__all__ = [
    'ConfigRepository',
    'GuildConfigDocument',
    'MongoStorage',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'SystemConfigDocument',
    'ThemeDocument',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
    'init_database',
]
