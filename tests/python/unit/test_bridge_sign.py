# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_bridge_sign | bot/server signing must produce identical headers."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

import pytest


pytestmark = pytest.mark.unit


def test_sign_symmetry_get():
    """bot's hmac.sign and server's _sign must produce byte-identical headers."""
    from attu_server.bridge_client import _sign as server_sign
    from doom_bot.bridge.hmac import sign as bot_sign

    secret = 'test-secret-32-bytes-or-so-here-yes'
    ts = 1746000000

    bot = bot_sign(secret, 'GET', '/bridge/guilds/123/channels', b'', timestamp=ts)
    srv = server_sign(secret, 'GET', '/bridge/guilds/123/channels', b'', timestamp=ts)

    assert bot == srv


def test_sign_symmetry_post_with_body():
    from attu_server.bridge_client import _sign as server_sign
    from doom_bot.bridge.hmac import sign as bot_sign

    secret = 'another-secret'
    ts = 1746000001
    body = b'{"signal_type":"theme"}'

    bot = bot_sign(secret, 'POST', '/bridge/reload', body, timestamp=ts)
    srv = server_sign(secret, 'POST', '/bridge/reload', body, timestamp=ts)

    assert bot == srv


def test_sign_changes_with_body():
    """signature must depend on the body so swapping payloads is rejected."""
    from doom_bot.bridge.hmac import sign

    a = sign('s', 'POST', '/bridge/reload', b'{"signal_type":"theme"}', timestamp=1)
    b = sign('s', 'POST', '/bridge/reload', b'{"signal_type":"system"}', timestamp=1)

    assert a != b


def test_sign_changes_with_method():
    from doom_bot.bridge.hmac import sign

    a = sign('s', 'GET', '/bridge/x', b'', timestamp=1)
    b = sign('s', 'POST', '/bridge/x', b'', timestamp=1)

    assert a != b


def test_sign_method_case_insensitive():
    """method case must not change the signature; verify normalizes to upper."""
    from doom_bot.bridge.hmac import sign

    a = sign('s', 'get', '/bridge/x', b'', timestamp=1)
    b = sign('s', 'GET', '/bridge/x', b'', timestamp=1)

    assert a == b
