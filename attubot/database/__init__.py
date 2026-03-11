"""
AttuBot - Database Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.database.connection import MongoStorage
from attubot.database.models import (
    ChatConfigDocument,
    ChatSourceDocument,
    FamilyDocument,
    GuildConfigDocument,
    MessageDocument,
    ReloadSignalDocument,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)
from attubot.database.repositories import (
    ChatConfigRepository,
    ChatSourceRepository,
    ConfigRepository,
    FamilyRepository,
    MessageRepository,
    ReloadSignalRepository,
    StarboardRepository,
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
    message_repo = MessageRepository(database)

    await marker_repo.init_indexes()
    logger.debug('marker indexes ready')

    await year_repo.init_indexes()
    logger.debug('year indexes ready')

    await signal_repo.init_indexes()
    logger.debug('signal indexes ready')

    await message_repo.init_indexes()
    logger.debug('message indexes ready')

    # seed module-level repo singletons so lazy _get_repo() calls work
    starboard_repo = StarboardRepository(database)
    await starboard_repo.init_indexes()
    logger.debug('starboard indexes ready')

    family_repo = FamilyRepository(database)
    await family_repo.init_indexes()
    logger.debug('family indexes ready')

    chat_config_repo = ChatConfigRepository(database)
    # ChatConfigRepository uses global_config collection; no dedicated index needed
    logger.debug('chat config repo ready')

    chat_source_repo = ChatSourceRepository(database)
    await chat_source_repo.init_indexes()
    logger.debug('chat source indexes ready')

    import attubot.families as _families
    import attubot.markers as _markers
    import attubot.messages as _messages
    import attubot.signals as _signals
    import attubot.starboard as _starboard
    import attubot.years as _years

    _families._family_repo = family_repo
    _markers._marker_repo = marker_repo
    _years._year_repo = year_repo
    _signals._repo = signal_repo
    _messages._message_repo = message_repo
    _starboard._starboard_repo = starboard_repo

    # wire chat repos into config so on_load() can use them
    config.chat_config_repo = chat_config_repo

    logger.info('database initialized')


__all__ = [
    'ChatConfigDocument',
    'ChatConfigRepository',
    'ChatSourceDocument',
    'ChatSourceRepository',
    'ConfigRepository',
    'FamilyDocument',
    'FamilyRepository',
    'GuildConfigDocument',
    'MessageDocument',
    'MessageRepository',
    'MongoStorage',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'StarboardRepository',
    'StarredMessageDocument',
    'SystemConfigDocument',
    'ThemeDocument',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
    'init_database',
]
