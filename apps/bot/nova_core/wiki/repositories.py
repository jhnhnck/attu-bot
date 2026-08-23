# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki.repositories | wiki repository classes."""

import asyncio

import structlog
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.wiki.documents import WikiViewDocument


logger = structlog.stdlib.get_logger(__name__)

_bg_tasks: set = set()


class WikiViewRepository:
    """repository for persistent wiki lookup view state."""

    COLLECTION = 'wiki_views'

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def init_indexes(self) -> None:
        await self.db[self.COLLECTION].create_index('message_id', unique=True)
        await self.db[self.COLLECTION].create_index('expires_at')

    async def upsert(self, doc: WikiViewDocument) -> None:
        """insert or update view state."""
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def get(self, message_id: int) -> WikiViewDocument | None:
        """fetch view state by message id."""
        raw = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if raw:
            raw.pop('_id', None)
            return WikiViewDocument(**raw)
        return None

    async def delete(self, message_id: int) -> None:
        """delete view state by message id."""
        await self.db[self.COLLECTION].delete_one({'message_id': message_id})

    async def delete_expired(self) -> int:
        """delete all expired view documents; returns count deleted."""
        import time

        result = await self.db[self.COLLECTION].delete_many({'expires_at': {'$lte': time.time()}})
        return result.deleted_count

    async def all_active(self) -> list[WikiViewDocument]:
        """return all non-expired view documents."""
        import time

        docs = await self.db[self.COLLECTION].find({'expires_at': {'$gt': time.time()}}).to_list(None)
        return [WikiViewDocument(**{k: v for k, v in d.items() if k != '_id'}) for d in docs]


async def _init_indexes(repo: WikiViewRepository) -> None:
    """init wiki_view repo indexes; errors logged, not raised."""
    try:
        await asyncio.wait_for(repo.init_indexes(), timeout=90.0)
        logger.debug('wiki_view indexes ready')
    except TimeoutError:
        logger.warning('wiki_view index init timed out after 90s (indexes may still be building in db)')
    except Exception as e:
        logger.warning(f'wiki_view index init failed (indexes may still be building): {e!s}')


def wire_wiki_command_repo(database: AsyncDatabase) -> WikiViewRepository:
    """create WikiViewRepository, wire it into commands.wiki, and schedule index init."""
    import nova_core.commands.wiki as _w

    repo = WikiViewRepository(database)
    _task = asyncio.ensure_future(_init_indexes(repo))
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)
    _w._wiki_view_repo = repo
    return repo
