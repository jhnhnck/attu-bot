"""
AttuBot - Database Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Documents, repositories, and MongoStorage live in the `attu_models` workspace
package; this module re-exports them so the existing `from attubot.database
import ...` sites keep working unchanged. `init_database()` and the bot-only
repo wiring stay here - the bot is the index-creation leader.
"""

import asyncio

from attu_models import (
    ConfigRepository,
    EggDocument,
    EggRepository,
    EggUserDocument,
    EggUserRepository,
    FamilyDocument,
    FamilyRepository,
    GuildConfigDocument,
    MessageDocument,
    MessageRepository,
    MongoStorage,
    ReloadSignalDocument,
    ReloadSignalRepository,
    ReminderDocument,
    ReminderRepository,
    StarboardRepository,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    WikiViewDocument,
    WikiViewRepository,
    YearDocument,
    YearMarkerDocument,
    YearMarkerRepository,
    YearRepository,
)
from attubot.logging import get_logger


logger = get_logger(__name__)


async def _try_init_indexes(repo: object, label: str, timeout_sec: float = 90.0) -> None:
    """Call repo.init_indexes(), logging a warning instead of raising on failure.

    FerretDB/DocumentDB builds RUM indexes non-concurrently and can block for minutes
    on large collections. This lets the bot start while indexes finish in the background.
    """
    try:
        await asyncio.wait_for(repo.init_indexes(), timeout=timeout_sec)  # type: ignore[union-attr]
        logger.debug(f'{label} indexes ready')
    except TimeoutError:
        logger.warn(f'{label} index init timed out after {timeout_sec:.0f}s (indexes may still be building in db)')
    except Exception as e:
        logger.warn(f'{label} index init failed (indexes may still be building): {e!s}')


def _wire_repos(*, family_repo, marker_repo, year_repo, signal_repo, message_repo, starboard_repo, egg_repo, egg_user_repo, wiki_view_repo, reminder_repo) -> None:
    """wire repository singletons into their respective modules after db init"""
    import attubot.client.families as _families
    import attubot.client.markers as _markers
    import attubot.client.messages as _messages
    import attubot.client.starboard as _starboard
    import attubot.client.years as _years
    import attubot.commands.wiki as _wiki
    import attubot.eggs.hatching as _hatching
    import attubot.signals as _signals
    import attubot.tasks.reminder as _reminder

    _families._family_repo = family_repo
    _markers._marker_repo = marker_repo
    _years._year_repo = year_repo
    _signals._repo = signal_repo
    _messages._message_repo = message_repo
    _starboard._starboard_repo = starboard_repo
    _hatching._egg_repo = egg_repo
    _hatching._egg_user_repo = egg_user_repo
    _wiki._wiki_view_repo = wiki_view_repo
    _reminder._reminder_repo = reminder_repo


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

    await _try_init_indexes(marker_repo, 'marker')
    await _try_init_indexes(year_repo, 'year')
    await _try_init_indexes(signal_repo, 'signal')
    await _try_init_indexes(message_repo, 'message')

    # seed module-level repo singletons so lazy _get_repo() calls work
    starboard_repo = StarboardRepository(database)
    await _try_init_indexes(starboard_repo, 'starboard')

    family_repo = FamilyRepository(database)
    await _try_init_indexes(family_repo, 'family')

    egg_repo = EggRepository(database)
    await _try_init_indexes(egg_repo, 'egg')

    egg_user_repo = EggUserRepository(database)
    await _try_init_indexes(egg_user_repo, 'egg_user')

    wiki_view_repo = WikiViewRepository(database)
    await _try_init_indexes(wiki_view_repo, 'wiki_view')

    reminder_repo = ReminderRepository(database)
    await _try_init_indexes(reminder_repo, 'reminder')

    _wire_repos(
        family_repo=family_repo,
        marker_repo=marker_repo,
        year_repo=year_repo,
        signal_repo=signal_repo,
        message_repo=message_repo,
        starboard_repo=starboard_repo,
        egg_repo=egg_repo,
        egg_user_repo=egg_user_repo,
        wiki_view_repo=wiki_view_repo,
        reminder_repo=reminder_repo,
    )

    logger.info('database initialized')


__all__ = [
    'ConfigRepository',
    'EggDocument',
    'EggRepository',
    'EggUserDocument',
    'EggUserRepository',
    'FamilyDocument',
    'FamilyRepository',
    'GuildConfigDocument',
    'MessageDocument',
    'MessageRepository',
    'MongoStorage',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'ReminderDocument',
    'ReminderRepository',
    'StarboardRepository',
    'StarredMessageDocument',
    'SystemConfigDocument',
    'ThemeDocument',
    'WikiViewDocument',
    'WikiViewRepository',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
    'init_database',
]
