# SPDX-License-Identifier: Apache-2.0
"""attu_models.connection | MongoDB connection manager with retry."""

import asyncio
import contextlib

import structlog
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConfigurationError, ConnectionFailure


logger = structlog.stdlib.get_logger(__name__)

_RETRY_DELAYS = (2.0, 4.0, 8.0)  # seconds between attempts 1→2, 2→3, 3→4


class MongoStorage:
    """MongoDB connection manager using pymongo async API."""

    def __init__(self):
        self.client: AsyncMongoClient | None = None
        self.db: AsyncDatabase | None = None
        self.mongo_url: str | None = None
        self.db_name: str | None = None

    async def connect(self, url: str, name: str, timeout: int = 30000, socket_timeout: int | None = 30000) -> AsyncDatabase:  # noqa: ASYNC109 - timeout parameter is for mongo client, not asyncio.timeout
        """initialize MongoDB connection with retry on transient failures.

        args:
            url: MongoDB connection URL (e.g. 'mongodb://localhost:27017')
            name: database name
            timeout: connection/server-selection timeout in milliseconds (default: 30000ms = 30s)
            socket_timeout: per-operation socket timeout in ms; None disables it (default: 30000ms = 30s)

        returns:
            AsyncDatabase: the connected database instance

        raises:
            RuntimeError: if all connection attempts fail
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
                    logger.exception(f'mongodb connection failed after {max_attempts} attempts')

            except Exception as e:
                last_err = e
                logger.exception('mongodb connection failed with unexpected error')
                break  # non-connection errors are not retried

        raise RuntimeError(f'MongoDB connection failed: {last_err!s}') from last_err

    def get_db(self) -> AsyncDatabase:
        """get the database instance."""
        if self.db is None:
            raise RuntimeError('MongoDB not initialized; call connect() first')
        return self.db

    async def close(self):
        """close the MongoDB connection."""
        if self.client:
            await self.client.close()
            logger.info('closed mongodb connection')
