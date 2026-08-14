# SPDX-License-Identifier: Apache-2.0
"""nova_core.starboard.repositories | starboard repository."""

import structlog
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.starboard.documents import StarredMessageDocument


logger = structlog.stdlib.get_logger(__name__)


class StarboardRepository:
    """Repository for starred message documents"""

    COLLECTION = 'starboard'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index('message_id', unique=True)
        await self.db[self.COLLECTION].create_index('guild_id')
        await self.db[self.COLLECTION].create_index('author_id')
        await self.db[self.COLLECTION].create_index('starboard_message_id')
        await self.db[self.COLLECTION].create_index('total_reactions')

    async def get(self, message_id: int) -> StarredMessageDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if doc:
            doc.pop('_id', None)
            return StarredMessageDocument(**doc)
        return None

    async def get_by_starboard_message(self, starboard_message_id: int) -> StarredMessageDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'starboard_message_id': starboard_message_id})
        if doc:
            doc.pop('_id', None)
            return StarredMessageDocument(**doc)
        return None

    async def upsert(self, doc: StarredMessageDocument):
        """insert or update a starred message document"""
        data = doc.model_dump()
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': data},
            upsert=True,
        )

    async def _sync_totals(self, message_id: int) -> StarredMessageDocument | None:
        """recompute and persist total_reactions and weighted_total atomically from stored arrays"""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            [
                {
                    '$set': {
                        'total_reactions': {
                            '$add': [
                                {'$sum': {'$map': {'input': {'$objectToArray': '$reactions'}, 'in': {'$size': '$$this.v'}}}},
                                {'$sum': {'$map': {'input': {'$objectToArray': '$super_reactions'}, 'in': {'$size': '$$this.v'}}}},
                            ]
                        },
                        'weighted_total': {
                            '$add': [
                                {'$toDouble': {'$sum': {'$map': {'input': {'$objectToArray': '$reactions'}, 'in': {'$size': '$$this.v'}}}}},
                                {'$multiply': [1.5, {'$toDouble': {'$sum': {'$map': {'input': {'$objectToArray': '$super_reactions'}, 'in': {'$size': '$$this.v'}}}}}]},
                            ]
                        },
                    }
                }
            ],
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return StarredMessageDocument(**result)

    async def add_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """add a user to the normal reaction list; skips if they already super-reacted for this emoji.

        returns the updated doc or None if the document was not found.
        """
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        # only update if the user is NOT already in super_reactions for this emoji
        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id, f'super_reactions.{emoji}': {'$ne': user_id}},
            {'$addToSet': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            # either doc not found or user already has a super reaction - fetch to distinguish
            existing = await self.db[self.COLLECTION].find_one({'message_id': message_id})
            if existing is None:
                return None
            existing.pop('_id', None)
            return StarredMessageDocument(**existing)
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def add_super_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """add a user to the super reaction list; removes them from normal reactions if present.

        returns the updated doc or None if the document was not found.
        """
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {
                '$addToSet': {f'super_reactions.{emoji}': user_id},
                '$pull': {f'reactions.{emoji}': user_id},
            },
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def remove_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """remove a user from the normal reaction list; returns the updated doc or None if not found"""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$pull': {f'reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def remove_super_reaction(self, message_id: int, emoji: str, user_id: int) -> StarredMessageDocument | None:
        """remove a user from the super reaction list; returns the updated doc or None if not found"""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$pull': {f'super_reactions.{emoji}': user_id}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def clear_emoji_reactions(self, message_id: int, emoji: str) -> StarredMessageDocument | None:
        """clear all normal and super reactions for a specific emoji; returns updated doc or None if not found."""
        if '.' in emoji:
            logger.warn(f'starboard: rejected emoji with dot in name: {emoji!r}')
            return None
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$unset': {f'reactions.{emoji}': '', f'super_reactions.{emoji}': ''}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def clear_all_reactions(self, message_id: int) -> StarredMessageDocument | None:
        """clear all reactions (all emojis, normal and super) from a message; returns updated doc or None if not found."""
        from pymongo import ReturnDocument

        result = await self.db[self.COLLECTION].find_one_and_update(
            {'message_id': message_id},
            {'$set': {'reactions': {}, 'super_reactions': {}}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return await self._sync_totals(message_id)

    async def set_starboard_message(self, message_id: int, starboard_message_id: int | None):
        """link or unlink a starboard channel post to this document"""
        result = await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'starboard_message_id': starboard_message_id}},
        )
        if result.matched_count == 0:
            logger.warn(f'starboard: set_starboard_message matched 0 docs for message_id {message_id}')

    async def set_reply_created(self, message_id: int):
        """mark that a reply post has been sent for an uneditable predecessor post"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'reply_created': True}},
        )

    async def delete(self, message_id: int) -> bool:
        """delete a starred message document by message_id; returns True if a document was deleted"""
        result = await self.db[self.COLLECTION].delete_one({'message_id': message_id})
        return result.deleted_count > 0

    async def get_random(self, guild_id: int, min_total: int, max_total: int | None = None) -> StarredMessageDocument | None:
        """return a random document matching the total_reactions range using $sample"""
        match: dict = {'guild_id': guild_id, 'total_reactions': {'$gte': min_total}}
        if max_total is not None:
            match['total_reactions']['$lte'] = max_total
        pipeline = [{'$match': match}, {'$sample': {'size': 1}}]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        if docs:
            docs[0].pop('_id', None)
            return StarredMessageDocument(**docs[0])
        return None

    async def leaderboard_most_stars(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by total stars received (sum of all reaction list lengths on their messages)"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$project': {'author_id': 1, 'reactions_arr': {'$objectToArray': '$reactions'}}},
            {'$unwind': '$reactions_arr'},
            {'$project': {'author_id': 1, 'count': {'$size': '$reactions_arr.v'}}},
            {'$group': {'_id': '$author_id', 'total_stars': {'$sum': '$count'}}},
            {'$sort': {'total_stars': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_starred(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by number of messages that reached the starboard"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}},
            {'$group': {'_id': '$author_id', 'starred_messages': {'$sum': 1}}},
            {'$sort': {'starred_messages': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_given(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by total stars given across all emojis"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$project': {'reactions_arr': {'$objectToArray': '$reactions'}}},
            {'$unwind': '$reactions_arr'},
            {'$unwind': '$reactions_arr.v'},
            {'$group': {'_id': '$reactions_arr.v', 'total_given': {'$sum': 1}}},
            {'$sort': {'total_given': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def total_for_guild(self, guild_id: int) -> int:
        """count of all starred message documents for a guild"""
        return await self.db[self.COLLECTION].count_documents({'guild_id': guild_id})

    async def sum_reactions_for_guild(self, guild_id: int) -> int:
        """sum of total_reactions across all documents for a guild"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {'$group': {'_id': None, 'total': {'$sum': '$total_reactions'}}},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        return docs[0]['total'] if docs else 0

    async def all_for_guild(self, guild_id: int) -> list[StarredMessageDocument]:
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [StarredMessageDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def mark_source_deleted(self, message_id: int) -> None:
        """mark a starred doc's source message as deleted so backfill skips it"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'source_deleted': True}},
        )

    async def get_all_pending(self, guild_id: int) -> list[StarredMessageDocument]:
        """return starred docs that have not yet been posted to the starboard channel"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id, 'starboard_message_id': None, 'source_deleted': {'$ne': True}})
        docs = await cursor.to_list(length=None)
        return [StarredMessageDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]
