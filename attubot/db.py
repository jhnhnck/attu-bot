"""
AttuBot - MongoDB Connection Management
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv

from pymongo import AsyncDatabase, AsyncMongoClient

from attubot.logging import get_logger

logger = get_logger(__name__)


class MongoStorage:
    """MongoDB connection manager using pymongo async API"""

    def __init__(self):
        self.client: AsyncMongoClient | None = None
        self.db: AsyncDatabase | None = None
        self.mongo_url: str = getenv('MONGODB_URL', 'mongodb://localhost:27017')
        self.db_name: str = getenv('MONGODB_DATABASE', 'doombot')

    async def connect(self) -> AsyncDatabase:
        """Initialize MongoDB connection"""
        logger.info(f'Connecting to MongoDB: {self.mongo_url}/{self.db_name}')
        self.client = AsyncMongoClient(self.mongo_url)
        self.db = self.client[self.db_name]
        return self.db

    def get_db(self) -> AsyncDatabase:
        """Get database instance"""
        if self.db is None:
            raise RuntimeError('MongoDB not initialized - call connect() first')
        return self.db

    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            await self.client.close()
            logger.info('Closed MongoDB connection')
