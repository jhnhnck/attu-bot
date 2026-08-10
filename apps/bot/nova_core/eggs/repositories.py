# SPDX-License-Identifier: Apache-2.0
"""nova_core.eggs.repositories | mongodb repositories for the eggs feature."""

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.eggs.documents import EggDocument, EggUserDocument


class EggRepository:
    """Repository for egg collection documents"""

    COLLECTION = 'eggs'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index('egg_id', unique=True)
        # covers get_oldest_ready() and get_next_unhatched() filter + sort on hatches_at
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('user_id', ASCENDING), ('hatched', ASCENDING), ('hatches_at', ASCENDING)],
        )

    async def insert(self, doc: EggDocument) -> None:
        """Insert a new egg"""
        await self.db[self.COLLECTION].insert_one(doc.model_dump())

    async def get(self, egg_id: str) -> EggDocument | None:
        """Fetch egg by egg_id"""
        doc = await self.db[self.COLLECTION].find_one({'egg_id': egg_id})
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_oldest_ready(self, guild_id: int, user_id: int) -> EggDocument | None:
        """Fetch the oldest unhatched egg that is ready to hatch"""
        import time

        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False, 'hatches_at': {'$lte': time.time()}},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_next_unhatched(self, guild_id: int, user_id: int) -> EggDocument | None:
        """Fetch the next unhatched egg (soonest hatches_at)"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def mark_hatched(self, egg_id: str, result: str) -> None:
        """Mark an egg as hatched and set its result"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'hatched': True, 'result': result}},
        )

    async def update_message_id(self, egg_id: str, message_id: int) -> None:
        """Store the thread message id for this egg"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'message_id': message_id}},
        )

    async def count_hatched(self) -> int:
        """Return total count of hatched eggs across all guilds"""
        return await self.db[self.COLLECTION].count_documents({'hatched': True})

    async def get_user_egg_stats(self, guild_id: int, user_id: int) -> 'tuple[int, int, dict[str, int]]':
        """Return (total_collected, total_hatched, unique_results_per_rarity) in one query.

        unique_results_per_rarity maps rarity -> count of distinct creature emojis hatched.
        """
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id},
            projection={'rarity': 1, 'result': 1, 'hatched': 1, '_id': 0},
        )
        total_collected = 0
        total_hatched = 0
        seen: dict[str, set[str]] = {}
        async for doc in cursor:
            total_collected += 1
            if doc.get('hatched'):
                total_hatched += 1
                rarity = doc['rarity']
                result = doc.get('result') or ''
                if result:
                    seen.setdefault(rarity, set()).add(result)
        return total_collected, total_hatched, {r: len(s) for r, s in seen.items()}

    async def leaderboard_most_hatched(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Return top users by total hatched egg count for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'hatched': True}},
            {'$group': {'_id': '$user_id', 'total': {'$sum': 1}}},
            {'$sort': {'total': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def leaderboard_most_unique(self, guild_id: int, limit: int = 10) -> list[dict]:
        """Return top users by count of distinct hatched creature types for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'hatched': True, 'result': {'$ne': None}}},
            {'$group': {'_id': {'user_id': '$user_id', 'result': '$result'}}},
            {'$group': {'_id': '$_id.user_id', 'unique': {'$sum': 1}}},
            {'$sort': {'unique': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=None)

    async def transfer(self, egg_id: str, new_user_id: int, new_message_id: int) -> None:
        """Transfer egg ownership and update its thread message id"""
        await self.db[self.COLLECTION].update_one(
            {'egg_id': egg_id},
            {'$set': {'user_id': new_user_id, 'message_id': new_message_id}},
        )

    async def get_oldest_unhatched_by_rarity(self, guild_id: int, user_id: int, rarity: str) -> 'EggDocument | None':
        """Fetch the oldest unhatched egg of a specific rarity for a user"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False, 'rarity': rarity},
            sort=[('hatches_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def get_oldest_hatched_by_result(self, guild_id: int, user_id: int, result: str) -> 'EggDocument | None':
        """Fetch the oldest hatched egg with a specific result emoji for a user"""
        doc = await self.db[self.COLLECTION].find_one(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': True, 'result': result},
            sort=[('collected_at', ASCENDING)],
        )
        if doc:
            doc.pop('_id', None)
            return EggDocument(**doc)
        return None

    async def list_unhatched(self, guild_id: int, user_id: int) -> 'list[EggDocument]':
        """Return all unhatched eggs for a user, sorted by hatches_at ascending"""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': False},
            sort=[('hatches_at', ASCENDING)],
        )
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggDocument(**doc))
        return docs

    async def list_hatched(self, guild_id: int, user_id: int) -> 'list[EggDocument]':
        """Return all hatched eggs for a user, sorted by collected_at ascending"""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id, 'hatched': True},
            sort=[('collected_at', ASCENDING)],
        )
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggDocument(**doc))
        return docs


class EggUserRepository:
    """Repository for per-user egg state documents"""

    COLLECTION = 'egg_users'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self) -> None:
        """Create required indexes"""
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('user_id', ASCENDING)],
            unique=True,
        )

    async def get(self, guild_id: int, user_id: int) -> EggUserDocument | None:
        """Fetch user egg state"""
        doc = await self.db[self.COLLECTION].find_one({'guild_id': guild_id, 'user_id': user_id})
        if doc:
            doc.pop('_id', None)
            return EggUserDocument(**doc)
        return None

    async def upsert(self, doc: EggUserDocument) -> None:
        """Insert or update user egg state"""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': doc.guild_id, 'user_id': doc.user_id},
            {'$set': doc.model_dump()},
            upsert=True,
        )

    async def update_field(self, guild_id: int, user_id: int, field: str, value) -> None:
        """Update a single field on the user egg state"""
        await self.db[self.COLLECTION].update_one(
            {'guild_id': guild_id, 'user_id': user_id},
            {'$set': {field: value}},
            upsert=True,
        )

    async def list_all(self, guild_id: int) -> list[EggUserDocument]:
        """Return all egg user documents for a guild"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = []
        async for doc in cursor:
            doc.pop('_id', None)
            docs.append(EggUserDocument(**doc))
        return docs
