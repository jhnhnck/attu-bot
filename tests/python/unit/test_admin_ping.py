# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_admin_ping | admin /ping requires a valid bearer token."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


pytestmark = pytest.mark.unit


@pytest.fixture
def client():
    from attu_server.config import AuthConfig, BridgeConfig, DatabaseConfig, ServerConfig, WebConfig
    from attu_server.main import create_app

    cfg = ServerConfig(
        database=DatabaseConfig(url='mongodb://localhost:27017', name='test'),
        web=WebConfig(secret_key='test-session-secret'),
        bridge=BridgeConfig(secret='test-bridge-secret'),
        auth=AuthConfig(api_keys=['valid-key']),
    )

    @asynccontextmanager
    async def _noop_lifespan(app: FastAPI):
        app.state.config = cfg
        yield

    with patch('attu_server.main._build_lifespan', return_value=_noop_lifespan):
        app = create_app(cfg)

    with TestClient(app) as tc:
        yield tc


def test_ping_missing_auth(client):
    """no Authorization header -> 401."""
    r = client.get('/api/admin/ping')
    assert r.status_code == 401


def test_ping_wrong_key(client):
    """valid header shape but key not in api_keys -> 401."""
    r = client.get('/api/admin/ping', headers={'Authorization': 'Bearer wrong-key'})
    assert r.status_code == 401


def test_ping_valid_key(client):
    """correct bearer token -> 200 {"ok": true}."""
    r = client.get('/api/admin/ping', headers={'Authorization': 'Bearer valid-key'})
    assert r.status_code == 200
    assert r.json() == {'ok': True}
