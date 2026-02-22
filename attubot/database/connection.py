"""
AttuBot - MongoDB Connection Management
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from attubot.logging import get_logger

logger = get_logger(__name__)


class MongoStorage:
    """MongoDB connection manager using pymongo async API"""

    def __init__(self):
        self.client: AsyncMongoClient | None = None
        self.db: AsyncDatabase | None = None
        self.mongo_url: str | None = None
        self.db_name: str | None = None

    async def connect(self, url: str, name: str, timeout: int = 10000) -> AsyncDatabase:  # noqa: ASYNC109
        """Initialize MongoDB connection with timeout

        Args:
            url: MongoDB connection URL (e.g. "mongodb://localhost:27017")
            name: Database name
            timeout: Connection timeout in milliseconds (default: 10000ms = 10s)

        Returns:
            AsyncDatabase: The connected database instance

        Raises:
            RuntimeError: If connection fails or times out
        """
        self.mongo_url = url
        self.db_name = name
        logger.info(f'Connecting to MongoDB: {self.mongo_url}/{self.db_name}')

        try:
            # Create client with timeout settings
            self.client = AsyncMongoClient(
                self.mongo_url,
                serverSelectionTimeoutMS=timeout,
                connectTimeoutMS=timeout,
            )

            # Verify connection by pinging the database
            await asyncio.wait_for(
                self.client.admin.command('ping'),
                timeout=timeout / 1000,  # Convert to seconds
            )

            self.db = self.client[self.db_name]
            logger.info('MongoDB connection established successfully')
            return self.db

        except TimeoutError:
            logger.error(f'MongoDB connection timed out after {timeout}ms')
            raise RuntimeError(f'MongoDB connection timeout: {self.mongo_url}')

        except Exception as e:
            logger.error(f'MongoDB connection failed: {e!s}')
            raise RuntimeError(f'MongoDB connection failed: {e!s}') from e

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
