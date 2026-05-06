"""
AttuBot - MongoDB Connection Management
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import contextlib

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConfigurationError, ConnectionFailure

from doom_bot.logging import get_logger


logger = get_logger(__name__)

_RETRY_DELAYS = (2.0, 4.0, 8.0)  # seconds between attempts 1→2, 2→3, 3→4


class MongoStorage:
    """MongoDB connection manager using pymongo async API"""

    def __init__(self):
        self.client: AsyncMongoClient | None = None
        self.db: AsyncDatabase | None = None
        self.mongo_url: str | None = None
        self.db_name: str | None = None

    async def connect(self, url: str, name: str, timeout: int = 30000, socket_timeout: int | None = 30000) -> AsyncDatabase:  # noqa: ASYNC109 - timeout parameter is for mongo client, not asyncio.timeout
        """Initialize MongoDB connection with retry on transient failures.

        Args:
            url: MongoDB connection URL (e.g. 'mongodb://localhost:27017')
            name: Database name
            timeout: Connection/server-selection timeout in milliseconds (default: 30000ms = 30s)
            socket_timeout: Per-operation socket timeout in ms; None disables it (default: 30000ms = 30s)

        Returns:
            AsyncDatabase: The connected database instance

        Raises:
            RuntimeError: If all connection attempts fail
        """
        self.mongo_url = url
        self.db_name = name

        max_attempts = len(_RETRY_DELAYS) + 1
        last_err: Exception | None = None

        for attempt in range(1, max_attempts + 1):
            logger.info(f'connecting to mongodb: {self.db_name} (attempt {attempt}/{max_attempts})')

            # close any client left over from a previous failed attempt
            if self.client is not None:
                with contextlib.suppress(Exception):
                    await self.client.close()
                self.client = None

            try:
                self.client = AsyncMongoClient(
                    self.mongo_url,
                    serverSelectionTimeoutMS=timeout,
                    connectTimeoutMS=timeout,
                    socketTimeoutMS=socket_timeout,
                    maxIdleTimeMS=300000,
                )
                await self.client.admin.command('ping')
                self.db = self.client[self.db_name]
                logger.info('mongodb connection established')
                return self.db

            except ConfigurationError:
                # bad url or client config; not retryable
                raise

            except ConnectionFailure as e:
                last_err = e
                if attempt < max_attempts:
                    delay = _RETRY_DELAYS[attempt - 1]
                    logger.warn(f'mongodb connection attempt {attempt} failed: {e!s}; retrying in {delay:.0f}s')
                    await asyncio.sleep(delay)
                else:
                    logger.error(f'mongodb connection failed after {max_attempts} attempts: {e!s}')

            except Exception as e:
                last_err = e
                logger.error(f'mongodb connection failed with unexpected error: {e!s}')
                break  # non-connection errors are not retried

        raise RuntimeError(f'MongoDB connection failed: {last_err!s}') from last_err

    def get_db(self) -> AsyncDatabase:
        """Get database instance"""
        if self.db is None:
            raise RuntimeError('MongoDB not initialized; call connect() first')
        return self.db

    async def close(self):
        """Close MongoDB connection"""
        if self.client:
            await self.client.close()
            logger.info('closed mongodb connection')
