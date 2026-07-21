# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_bridge_auth | bridge router rejects unsigned/stale/forged requests."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


pytestmark = pytest.mark.unit


@pytest.fixture
def bridge_config():
    """install a minimal BridgeConfig on the doom_bot config singleton for the test."""
    from doom_bot import config
    from doom_bot.config import BridgeConfig

    config.bridge = BridgeConfig(secret='unit-test-secret', bot_port=5050, replay_window=60)
    yield config.bridge
    config.bridge = None


@pytest.fixture
def client(bridge_config):
    """build the bridge fastapi app with discord lookups patched out."""
    from doom_bot.bridge.router import build_app

    # discord_integration calls would touch pycord; not exercised here
    with patch('doom_bot.bridge.router.di'):
        app = build_app()
        with TestClient(app) as tc:
            yield tc


def _sign(secret: str, method: str, path: str, body: bytes, ts: int) -> str:
    import hashlib
    import hmac

    payload = f'{ts}\n{method.upper()}\n{path}\n'.encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f't={ts},v1={digest}'


# --- /bridge/health is unsigned ---


def test_health_unsigned_ok(client):
    r = client.get('/bridge/health')
    assert r.status_code == 200
    body = r.json()
    assert body['status'] == 'ok'
    assert 'schema' in body
    assert 'config_version' in body


# --- signed endpoints reject unauthenticated requests ---


def test_invalidate_cache_missing_signature(client):
    r = client.post('/bridge/cache/invalidate', json={'guild_id': 1})
    assert r.status_code == 401
    assert 'missing' in r.json()['detail']


def test_invalidate_cache_malformed_signature(client):
    r = client.post('/bridge/cache/invalidate', json={'guild_id': 1}, headers={'x-bridge-signature': 'garbage'})
    assert r.status_code == 401
    assert 'malformed' in r.json()['detail']


def test_invalidate_cache_stale_timestamp(client, bridge_config):
    body = b'{"guild_id":1}'
    stale_ts = int(time.time()) - bridge_config.replay_window - 5
    sig = _sign(bridge_config.secret, 'POST', '/bridge/cache/invalidate', body, stale_ts)

    r = client.post('/bridge/cache/invalidate', content=body, headers={'x-bridge-signature': sig, 'content-type': 'application/json'})
    assert r.status_code == 401
    assert 'stale' in r.json()['detail']


def test_invalidate_cache_wrong_secret(client, bridge_config):
    body = b'{"guild_id":1}'
    ts = int(time.time())
    sig = _sign('wrong-secret', 'POST', '/bridge/cache/invalidate', body, ts)

    r = client.post('/bridge/cache/invalidate', content=body, headers={'x-bridge-signature': sig, 'content-type': 'application/json'})
    assert r.status_code == 401
    assert 'invalid' in r.json()['detail']


def test_invalidate_cache_tampered_body(client, bridge_config):
    """signed for one body, posted with another -> rejected"""
    signed_body = b'{"guild_id":1}'
    actual_body = b'{"guild_id":2}'
    ts = int(time.time())
    sig = _sign(bridge_config.secret, 'POST', '/bridge/cache/invalidate', signed_body, ts)

    r = client.post('/bridge/cache/invalidate', content=actual_body, headers={'x-bridge-signature': sig, 'content-type': 'application/json'})
    assert r.status_code == 401


def test_invalidate_cache_valid_signature(client, bridge_config):
    body = b'{"guild_id":1}'
    ts = int(time.time())
    sig = _sign(bridge_config.secret, 'POST', '/bridge/cache/invalidate', body, ts)

    r = client.post('/bridge/cache/invalidate', content=body, headers={'x-bridge-signature': sig, 'content-type': 'application/json'})
    assert r.status_code == 200
    assert r.json() == {'success': True}
