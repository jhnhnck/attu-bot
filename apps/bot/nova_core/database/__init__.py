# SPDX-License-Identifier: Apache-2.0
"""nova_core.database | database package.

Documents, repositories, and MongoStorage live in the `attu_models` workspace
package; this module re-exports them so the existing `from nova_core.database
import ...` sites keep working unchanged. `init_database()` and the bot-only
repo wiring stay here - the bot is the index-creation leader.
"""

import asyncio

import structlog

from attu_models import (
    ConfigRepository,
    GuildConfigDocument,
    MessageDocument,
    MessageRepository,
    MongoStorage,
    ReloadSignalDocument,
    ReloadSignalRepository,
    StarboardRepository,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
    YearMarkerRepository,
    YearRepository,
)


logger = structlog.stdlib.get_logger(__name__)


async def _try_init_indexes(repo: object, label: str, timeout_sec: float = 90.0) -> None:
    """Call repo.init_indexes(), logging a warning instead of raising on failure.

    FerretDB/DocumentDB builds RUM indexes non-concurrently and can block for minutes
    on large collections. This lets the bot start while indexes finish in the background.
    """
    try:
        await asyncio.wait_for(repo.init_indexes(), timeout=timeout_sec)  # type: ignore[union-attr]
        logger.debug(f'{label} indexes ready')
    except TimeoutError:
        logger.warning(f'{label} index init timed out after {timeout_sec:.0f}s (indexes may still be building in db)')
    except Exception as e:
        logger.warning(f'{label} index init failed (indexes may still be building): {e!s}')


def _wire_repos(
    *,
    marker_repo,
    year_repo,
    signal_repo,
    message_repo,
    starboard_repo,
) -> None:
    """wire repository singletons into their respective modules after db init"""
    import nova_core.client.markers as _markers
    import nova_core.client.messages as _messages
    import nova_core.client.starboard as _starboard
    import nova_core.client.years as _years
    import nova_core.signals as _signals

    _markers._marker_repo = marker_repo
    _years._year_repo = year_repo
    _signals._repo = signal_repo
    _messages._message_repo = message_repo
    _starboard._starboard_repo = starboard_repo


async def init_database(url: str, name: str):
    """Connect to MongoDB and initialize all repository indexes.

    Args:
        url: MongoDB connection URL
        name: Database name
    """
    from nova_core.client.core import config, db

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

    _wire_repos(
        marker_repo=marker_repo,
        year_repo=year_repo,
        signal_repo=signal_repo,
        message_repo=message_repo,
        starboard_repo=starboard_repo,
    )

    logger.info('database initialized')


__all__ = [
    'ConfigRepository',
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
