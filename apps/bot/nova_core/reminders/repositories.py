# SPDX-License-Identifier: Apache-2.0
"""nova_core.reminders.repositories | reminder repository class."""

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.reminders.documents import ReminderDocument


class ReminderRepository:
    """Repository for scheduled in-universe date reminders"""

    COLLECTION = 'reminders'

    def __init__(self, db: AsyncDatabase) -> None:
        self.db = db

    async def init_indexes(self) -> None:
        await self.db[self.COLLECTION].create_index('reminder_id', unique=True)
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('fired', ASCENDING), ('attu_year', ASCENDING)],
        )
        await self.db[self.COLLECTION].create_index(
            [('guild_id', ASCENDING), ('user_id', ASCENDING), ('fired', ASCENDING)],
        )

    async def insert(self, doc: ReminderDocument) -> None:
        await self.db[self.COLLECTION].insert_one(doc.model_dump())

    async def get(self, reminder_id: str) -> ReminderDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'reminder_id': reminder_id})
        if doc:
            doc.pop('_id', None)
            return ReminderDocument(**doc)
        return None

    async def get_by_prefix(self, prefix: str, guild_id: int, user_id: int) -> ReminderDocument | None:
        """Fetch a reminder by id prefix (first 8 chars), scoped to guild + user"""
        import re

        pattern = f'^{re.escape(prefix)}'
        doc = await self.db[self.COLLECTION].find_one({
            'reminder_id': {'$regex': pattern},
            'guild_id': guild_id,
            'user_id': user_id,
        })
        if doc:
            doc.pop('_id', None)
            return ReminderDocument(**doc)
        return None

    async def update_message_id(self, reminder_id: str, message_id: int) -> None:
        """Store the bot response message id for jump URL construction"""
        await self.db[self.COLLECTION].update_one(
            {'reminder_id': reminder_id},
            {'$set': {'message_id': message_id}},
        )

    async def list_active_for_user(self, guild_id: int, user_id: int) -> list[ReminderDocument]:
        """Return all unfired reminders for a user in a guild, sorted by target date"""
        cursor = self.db[self.COLLECTION].find(
            {'guild_id': guild_id, 'user_id': user_id, 'fired': False},
            sort=[('attu_year', ASCENDING), ('attu_month', ASCENDING), ('attu_day', ASCENDING)],
        )
        docs = await cursor.to_list(None)
        return [ReminderDocument(**{k: v for k, v in d.items() if k != '_id'}) for d in docs]

    async def list_all_unfired(self) -> list[ReminderDocument]:
        """Return all unfired reminders across all guilds"""
        docs = await self.db[self.COLLECTION].find({'fired': False}).to_list(None)
        return [ReminderDocument(**{k: v for k, v in d.items() if k != '_id'}) for d in docs]

    async def mark_fired(self, reminder_id: str, fired_at: int) -> None:
        await self.db[self.COLLECTION].update_one(
            {'reminder_id': reminder_id},
            {'$set': {'fired': True, 'fired_at': fired_at}},
        )

    async def delete(self, reminder_id: str) -> bool:
        """Delete a reminder; returns True if a document was deleted"""
        result = await self.db[self.COLLECTION].delete_one({'reminder_id': reminder_id})
        return result.deleted_count > 0
