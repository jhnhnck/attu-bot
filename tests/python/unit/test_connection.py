"""
AttuBot - Unit Tests for MongoDB Connection Management
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pymongo.errors import ConfigurationError, ConnectionFailure

from nova_core.database.connection import MongoStorage


pytestmark = pytest.mark.unit


# ============================================================
# helpers
# ============================================================


def _make_mock_client(*, ping_side_effect=None):
    """build a mock AsyncMongoClient with configurable ping behavior"""
    mock_client = MagicMock()
    mock_client.admin.command = AsyncMock(side_effect=ping_side_effect)
    mock_client.close = AsyncMock()
    mock_client.__getitem__ = MagicMock(return_value=MagicMock())
    return mock_client


# ============================================================
# connect() — happy path
# ============================================================


class TestConnectHappyPath:
    """unit: connect() succeeds on first attempt and returns the database"""

    async def test_connects_and_pings_on_first_try(self):
        mock_client = _make_mock_client()
        mock_db = MagicMock()
        mock_client.__getitem__ = MagicMock(return_value=mock_db)

        storage = MongoStorage()
        with patch('attu_models.connection.AsyncMongoClient', return_value=mock_client):
            result = await storage.connect('mongodb://localhost:27017', 'testdb')

        assert result is mock_db
        mock_client.admin.command.assert_awaited_once_with('ping')

    async def test_stores_url_and_name(self):
        mock_client = _make_mock_client()

        storage = MongoStorage()
        with patch('attu_models.connection.AsyncMongoClient', return_value=mock_client):
            await storage.connect('mongodb://host:1234', 'mydb')

        assert storage.mongo_url == 'mongodb://host:1234'
        assert storage.db_name == 'mydb'

    async def test_client_constructed_with_timeout_params(self):
        mock_client = _make_mock_client()

        storage = MongoStorage()
        with patch('attu_models.connection.AsyncMongoClient', return_value=mock_client) as mock_cls:
            await storage.connect('mongodb://localhost:27017', 'testdb', timeout=5000, socket_timeout=10000)

        mock_cls.assert_called_once_with(
            'mongodb://localhost:27017',
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=10000,
            maxIdleTimeMS=300000,
        )


# ============================================================
# connect() — retry on ConnectionFailure
# ============================================================


class TestConnectRetry:
    """unit: connect() retries on transient ConnectionFailure"""

    async def test_succeeds_on_second_attempt(self):
        mock_client_fail = _make_mock_client(ping_side_effect=ConnectionFailure('refused'))
        mock_client_ok = _make_mock_client()
        mock_db = MagicMock()
        mock_client_ok.__getitem__ = MagicMock(return_value=mock_db)

        call_count = 0

        def client_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_client_fail
            return mock_client_ok

        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', side_effect=client_factory),
            patch('attu_models.connection.asyncio.sleep', new_callable=AsyncMock) as mock_sleep,
        ):
            result = await storage.connect('mongodb://localhost:27017', 'testdb')

        assert result is mock_db
        mock_sleep.assert_awaited_once_with(2.0)

    async def test_closes_failed_client_before_retry(self):
        mock_client_fail = _make_mock_client(ping_side_effect=ConnectionFailure('refused'))
        mock_client_ok = _make_mock_client()

        call_count = 0

        def client_factory(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 1:
                return mock_client_fail
            return mock_client_ok

        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', side_effect=client_factory),
            patch('attu_models.connection.asyncio.sleep', new_callable=AsyncMock),
        ):
            await storage.connect('mongodb://localhost:27017', 'testdb')

        # the failed client should have been closed during cleanup at the start of attempt 2
        mock_client_fail.close.assert_awaited()


# ============================================================
# connect() — ConfigurationError (no retry)
# ============================================================


class TestConnectConfigurationError:
    """unit: connect() raises immediately on ConfigurationError without retrying"""

    async def test_raises_configuration_error_immediately(self):
        mock_client = MagicMock()
        mock_client.admin.command = AsyncMock(side_effect=ConfigurationError('bad url'))
        mock_client.close = AsyncMock()

        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', return_value=mock_client),
            patch('attu_models.connection.asyncio.sleep', new_callable=AsyncMock) as mock_sleep,
            pytest.raises(ConfigurationError, match='bad url'),
        ):
            await storage.connect('mongodb://bad-url', 'testdb')

        # sleep should never be called - no retry
        mock_sleep.assert_not_awaited()

    async def test_configuration_error_from_client_init(self):
        """ConfigurationError raised during client construction also propagates"""
        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', side_effect=ConfigurationError('invalid scheme')),
            pytest.raises(ConfigurationError, match='invalid scheme'),
        ):
            await storage.connect('not-a-url', 'testdb')


# ============================================================
# connect() — exhausts retries
# ============================================================


class TestConnectExhaustsRetries:
    """unit: connect() raises RuntimeError after all attempts fail"""

    async def test_all_attempts_fail_raises_runtime_error(self):
        mock_client = _make_mock_client(ping_side_effect=ConnectionFailure('still down'))

        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', return_value=mock_client),
            patch('attu_models.connection.asyncio.sleep', new_callable=AsyncMock) as mock_sleep,
            pytest.raises(RuntimeError, match='MongoDB connection failed'),
        ):
            await storage.connect('mongodb://localhost:27017', 'testdb')

        # should have slept between attempts (3 delays for 4 attempts)
        assert mock_sleep.await_count == 3

    async def test_unexpected_error_raises_without_retry(self):
        """non-ConnectionFailure exceptions break out of the loop immediately"""
        mock_client = _make_mock_client(ping_side_effect=OSError('network unreachable'))

        storage = MongoStorage()
        with (
            patch('attu_models.connection.AsyncMongoClient', return_value=mock_client),
            patch('attu_models.connection.asyncio.sleep', new_callable=AsyncMock) as mock_sleep,
            pytest.raises(RuntimeError, match='MongoDB connection failed'),
        ):
            await storage.connect('mongodb://localhost:27017', 'testdb')

        # no retries for unexpected errors
        mock_sleep.assert_not_awaited()


# ============================================================
# get_db()
# ============================================================


class TestGetDb:
    """unit: get_db() returns database or raises when not connected"""

    def test_returns_db_when_connected(self):
        storage = MongoStorage()
        mock_db = MagicMock()
        storage.db = mock_db

        assert storage.get_db() is mock_db

    def test_raises_when_not_connected(self):
        storage = MongoStorage()
        with pytest.raises(RuntimeError, match='MongoDB not initialized'):
            storage.get_db()


# ============================================================
# close()
# ============================================================


class TestClose:
    """unit: close() shuts down the client connection"""

    async def test_closes_client(self):
        storage = MongoStorage()
        mock_client = AsyncMock()
        storage.client = mock_client

        await storage.close()

        mock_client.close.assert_awaited_once()

    async def test_no_error_when_client_is_none(self):
        storage = MongoStorage()
        storage.client = None

        # should not raise
        await storage.close()
