# SPDX-License-Identifier: Apache-2.0
"""nova_core.trees.repositories | FamilyEcho family tree repository."""

import structlog
from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.trees.documents import FamilyDocument


logger = structlog.stdlib.get_logger(__name__)


class FamilyRepository:
    """repository for registered FamilyEcho family trees."""

    COLLECTION = 'families'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index([('guild_id', ASCENDING), ('name', ASCENDING)], unique=True)

    async def upsert(self, doc: FamilyDocument) -> None:
        """save or update a family record keyed by (guild_id, name)."""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': doc.guild_id, 'name': doc.name},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def get(self, guild_id: int, name: str) -> FamilyDocument | None:
        """fetch a family by guild and normalized name."""
        doc = await self.db[self.COLLECTION].find_one({'guild_id': guild_id, 'name': name})
        if doc:
            doc.pop('_id', None)
            return FamilyDocument(**doc)
        return None

    async def list_all(self, guild_id: int) -> list[FamilyDocument]:
        """list all registered families for a guild."""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [FamilyDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]
