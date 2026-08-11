# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.repositories | MongoDB repository classes for the ccboard feature."""

from pymongo import ASCENDING
from pymongo.asynchronous.database import AsyncDatabase

from nova_core.ccboard.documents import BoardEntryDocument, ReactionDocument


class ReactionRepository:
    """Repository for ccboard reaction documents (one per message_id, user_id).

    records are never hard-deleted; on remove, `removed` is set to True. on re-react with
    the same emoji, the existing doc is refreshed in place. on re-react with a different
    emoji, the existing doc is soft-deleted and a new one is created.
    """

    COLLECTION = 'ccboard_reactions'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        # natural primary key; one vote per (message, user) at the db level
        await self.db[self.COLLECTION].create_index([('message_id', ASCENDING), ('user_id', ASCENDING)], unique=True)
        await self.db[self.COLLECTION].create_index('guild_id')
        await self.db[self.COLLECTION].create_index('author_id')
        await self.db[self.COLLECTION].create_index('user_id')
        await self.db[self.COLLECTION].create_index([('message_id', ASCENDING), ('removed', ASCENDING)])

    async def get_active(self, message_id: int, user_id: int) -> ReactionDocument | None:
        """return the active (`removed=False`) reaction for this user on this message, if any"""
        doc = await self.db[self.COLLECTION].find_one({'message_id': message_id, 'user_id': user_id, 'removed': False})
        if doc:
            doc.pop('_id', None)
            return ReactionDocument(**doc)
        return None

    async def upsert_active(self, doc: ReactionDocument) -> None:
        """upsert a reaction doc as active. caller is responsible for soft-deleting any prior
        different-emoji record before calling this (one-vote enforcement step 8)."""
        data = doc.model_dump()
        data['removed'] = False
        data['removed_at'] = None
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id, 'user_id': doc.user_id},
            {'$set': data},
            upsert=True,
        )

    async def soft_delete(self, message_id: int, user_id: int, *, expected_emoji: str | None = None, now: int) -> ReactionDocument | None:
        """soft-delete the active reaction for (message_id, user_id).

        if `expected_emoji` is provided and the active doc's emoji does not match, returns
        None without modifying anything (this is the stale-echo case from spec step 8).
        returns the soft-deleted doc on success, or None if no active doc exists.
        """
        from pymongo import ReturnDocument

        match: dict = {'message_id': message_id, 'user_id': user_id, 'removed': False}
        if expected_emoji is not None:
            match['emoji_str'] = expected_emoji
        result = await self.db[self.COLLECTION].find_one_and_update(
            match,
            {'$set': {'removed': True, 'removed_at': now}},
            return_document=ReturnDocument.AFTER,
        )
        if result is None:
            return None
        result.pop('_id', None)
        return ReactionDocument(**result)

    async def soft_delete_all_for_message(self, message_id: int, *, now: int) -> int:
        """soft-delete every active reaction on this message; returns the number affected"""
        result = await self.db[self.COLLECTION].update_many(
            {'message_id': message_id, 'removed': False},
            {'$set': {'removed': True, 'removed_at': now}},
        )
        return result.modified_count

    async def soft_delete_emoji(self, message_id: int, emoji_str: str, *, now: int) -> int:
        """soft-delete every active reaction with this emoji on this message"""
        result = await self.db[self.COLLECTION].update_many(
            {'message_id': message_id, 'emoji_str': emoji_str, 'removed': False},
            {'$set': {'removed': True, 'removed_at': now}},
        )
        return result.modified_count

    async def aggregate_points(self, message_id: int) -> tuple[int, int]:
        """return (net_points, positive_points) for active reactions on this message"""
        pipeline = [
            {'$match': {'message_id': message_id, 'removed': False}},
            {
                '$group': {
                    '_id': None,
                    'net_points': {'$sum': '$point_value'},
                    'positive_points': {
                        '$sum': {'$cond': [{'$gt': ['$point_value', 0]}, '$point_value', 0]},
                    },
                }
            },
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        if not docs:
            return 0, 0
        return int(docs[0].get('net_points', 0)), int(docs[0].get('positive_points', 0))

    async def list_for_message(self, message_id: int, *, include_removed: bool = True) -> list[ReactionDocument]:
        """return all reactions on a message; for /debug ccboard show_reactions"""
        match: dict = {'message_id': message_id}
        if not include_removed:
            match['removed'] = False
        cursor = self.db[self.COLLECTION].find(match)
        docs = await cursor.to_list(length=None)
        return [ReactionDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def message_ids_with_emoji(self, guild_id: int, emoji_str: str) -> list[int]:
        """return distinct message_ids in this guild that have an active reaction with this emoji"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'emoji_str': emoji_str, 'removed': False}},
            {'$group': {'_id': '$message_id'}},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return [doc['_id'] for doc in await cursor.to_list(length=None)]

    async def leaderboard_most_given(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top users by count of active positive-point reactions given"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'removed': False, 'point_value': {'$gt': 0}}},
            {'$group': {'_id': '$user_id', 'total_given': {'$sum': 1}}},
            {'$sort': {'total_given': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)


class EntryRepository:
    """Repository for ccboard entry documents (one per tracked message)"""

    COLLECTION = 'ccboard_entries'

    def __init__(self, db: AsyncDatabase):
        self.db = db

    async def init_indexes(self):
        await self.db[self.COLLECTION].create_index('message_id', unique=True)
        await self.db[self.COLLECTION].create_index('guild_id')
        await self.db[self.COLLECTION].create_index('author_id')
        await self.db[self.COLLECTION].create_index('effective_author_id')
        await self.db[self.COLLECTION].create_index('starboard_message_id')
        # multikey index for redirect lookups from /stars command response messages
        await self.db[self.COLLECTION].create_index('display_message_ids')
        await self.db[self.COLLECTION].create_index('positive_points')
        await self.db[self.COLLECTION].create_index('last_reaction_at')
        # is_dirty + last_reaction_at compound supports the manager's settled-entries query
        await self.db[self.COLLECTION].create_index([('is_dirty', ASCENDING), ('last_reaction_at', ASCENDING)])

    async def get(self, message_id: int) -> BoardEntryDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'message_id': message_id})
        if doc:
            doc.pop('_id', None)
            return BoardEntryDocument(**doc)
        return None

    async def get_by_starboard_message(self, starboard_message_id: int) -> BoardEntryDocument | None:
        doc = await self.db[self.COLLECTION].find_one({'starboard_message_id': starboard_message_id})
        if doc:
            doc.pop('_id', None)
            return BoardEntryDocument(**doc)
        return None

    async def get_by_display_message(self, display_message_id: int) -> BoardEntryDocument | None:
        """find an entry whose display_message_ids array contains this id"""
        doc = await self.db[self.COLLECTION].find_one({'display_message_ids': display_message_id})
        if doc:
            doc.pop('_id', None)
            return BoardEntryDocument(**doc)
        return None

    async def upsert(self, doc: BoardEntryDocument) -> None:
        data = doc.model_dump()
        await self.db[self.COLLECTION].update_one(
            {'message_id': doc.message_id},
            {'$set': data},
            upsert=True,
        )

    async def set_starboard_message(self, message_id: int, starboard_message_id: int | None) -> None:
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'starboard_message_id': starboard_message_id}},
        )

    async def set_reply_created(self, message_id: int) -> None:
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'reply_created': True}},
        )

    async def append_display_message_id(self, message_id: int, display_message_id: int, *, cap: int = 20) -> None:
        """push a display message id, keeping only the most recent `cap` entries"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$push': {'display_message_ids': {'$each': [display_message_id], '$slice': -cap}}},
        )

    async def set_points(self, message_id: int, *, net_points: int, positive_points: int) -> None:
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'net_points': net_points, 'positive_points': positive_points}},
        )

    async def mark_dirty(self, message_id: int, *, last_reaction_at: int) -> None:
        """called by the watcher on every reaction event; flags the entry for manager pickup"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'is_dirty': True, 'last_reaction_at': last_reaction_at}},
        )

    async def mark_synced(self, message_id: int, *, now: int) -> None:
        """called by the manager after a successful sync"""
        await self.db[self.COLLECTION].update_one(
            {'message_id': message_id},
            {'$set': {'is_dirty': False, 'last_synced_at': now}},
        )

    async def mark_all_dirty(self, guild_id: int) -> int:
        """force the manager to rebuild every post in this guild on the next tick (/fix ccboard regen)"""
        result = await self.db[self.COLLECTION].update_many(
            {'guild_id': guild_id},
            {'$set': {'is_dirty': True}},
        )
        return result.modified_count

    async def find_settled(self, guild_id: int, *, now: int, debounce_seconds: int = 60, limit: int = 50) -> list[BoardEntryDocument]:
        """return up to `limit` dirty entries whose last reaction is at least `debounce_seconds` old"""
        cursor = (
            self
            .db[self.COLLECTION]
            .find({
                'guild_id': guild_id,
                'is_dirty': True,
                'last_reaction_at': {'$lte': now - debounce_seconds},
            })
            .limit(limit)
        )
        docs = await cursor.to_list(length=limit)
        return [BoardEntryDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def get_random(
        self,
        guild_id: int,
        *,
        min_positive: int = 1,
        max_positive: int | None = None,
        author_id: int | None = None,
        message_ids: list[int] | None = None,
        require_board_post: bool = True,
    ) -> BoardEntryDocument | None:
        """return a random entry matching the filters using $sample.

        `message_ids`, when provided, restricts to entries with one of these ids -- used by
        emoji-filtered random by first calling ReactionRepository.message_ids_with_emoji.
        `author_id` matches against (effective_author_id or author_id).
        `require_board_post=False` allows lost-message queries (entries below threshold with no board post).
        """
        match: dict = {'guild_id': guild_id, 'positive_points': {'$gte': min_positive}}
        if require_board_post:
            match['starboard_message_id'] = {'$ne': None}
        if max_positive is not None:
            match['positive_points']['$lte'] = max_positive
        if message_ids is not None:
            match['message_id'] = {'$in': message_ids}
        if author_id is not None:
            match['$or'] = [
                {'effective_author_id': author_id},
                {'effective_author_id': None, 'author_id': author_id},
            ]
        pipeline = [{'$match': match}, {'$sample': {'size': 1}}]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        docs = await cursor.to_list(length=1)
        if docs:
            docs[0].pop('_id', None)
            return BoardEntryDocument(**docs[0])
        return None

    async def delete(self, message_id: int) -> bool:
        """delete an entry doc; returns True if a document was deleted"""
        result = await self.db[self.COLLECTION].delete_one({'message_id': message_id})
        return result.deleted_count > 0

    async def all_for_guild(self, guild_id: int) -> list[BoardEntryDocument]:
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id})
        docs = await cursor.to_list(length=None)
        return [BoardEntryDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]

    async def distinct_channel_ids(self, guild_id: int) -> list[int]:
        """return distinct channel_ids of entries in this guild; used by discover_guild to scope channel scans."""
        result = await self.db[self.COLLECTION].distinct('channel_id', {'guild_id': guild_id})
        return [int(v) for v in result]

    async def recent_authors(self, guild_id: int, *, limit: int) -> list[int]:
        """return the credited author id of the last `limit` posted entries in chronological
        order, newest first; used by the sweep streak counter. credited author is
        effective_author_id when set, else author_id.
        """
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}, projection={'author_id': 1, 'effective_author_id': 1, 'last_synced_at': 1}).sort('last_synced_at', -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [doc.get('effective_author_id') or doc['author_id'] for doc in docs]

    async def leaderboard_most_stars(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top credited users by total positive_points received"""
        pipeline = [
            {'$match': {'guild_id': guild_id}},
            {
                '$group': {
                    '_id': {'$ifNull': ['$effective_author_id', '$author_id']},
                    'total_stars': {'$sum': '$positive_points'},
                },
            },
            {'$sort': {'total_stars': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_most_starred(self, guild_id: int, limit: int = 10) -> list[dict]:
        """top credited users by count of messages on the board"""
        pipeline = [
            {'$match': {'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}},
            {
                '$group': {
                    '_id': {'$ifNull': ['$effective_author_id', '$author_id']},
                    'starred_messages': {'$sum': 1},
                },
            },
            {'$sort': {'starred_messages': -1}},
            {'$limit': limit},
        ]
        cursor = await self.db[self.COLLECTION].aggregate(pipeline)
        return await cursor.to_list(length=limit)

    async def leaderboard_top_messages(self, guild_id: int, limit: int = 10) -> list[BoardEntryDocument]:
        """top messages by positive_points"""
        cursor = self.db[self.COLLECTION].find({'guild_id': guild_id, 'starboard_message_id': {'$ne': None}}).sort('positive_points', -1).limit(limit)
        docs = await cursor.to_list(length=limit)
        return [BoardEntryDocument(**{k: v for k, v in doc.items() if k != '_id'}) for doc in docs]
