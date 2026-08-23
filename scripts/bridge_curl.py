#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""scripts.bridge_curl | sign + send a request to the bot bridge.

usage:
  uv run scripts/bridge_curl.py GET /bridge/guilds/<id>/channels
  uv run scripts/bridge_curl.py POST /bridge/reload '{"signal_type":"theme"}'

reads the bridge secret from $ATTU_CONFIG_FILE (default ./.secrets/attu-bot.toml)
under [bridge].secret. talks to http://localhost:5050 by default; override with
the BRIDGE_URL env var (e.g. BRIDGE_URL=http://core:5050 inside compose).

prints the response status, headers, and body for inspection. exits non-zero on
http error.
"""

import hashlib
import hmac
import json
import os
import sys
import time
from pathlib import Path

import httpx
import tomlkit


def _sign(secret: str, method: str, path: str, body: bytes, ts: int) -> str:
    payload = f'{ts}\n{method.upper()}\n{path}\n'.encode() + body
    digest = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return f't={ts},v1={digest}'


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    method = sys.argv[1].upper()
    path = sys.argv[2]
    body_arg = sys.argv[3] if len(sys.argv) > 3 else ''

    config_path = Path(os.environ.get('ATTU_CONFIG_FILE', './.secrets/attu-bot.toml'))
    if not config_path.exists():
        print(f'config file not found: {config_path}', file=sys.stderr)
        return 1
    with config_path.open() as f:
        cfg = tomlkit.load(f)
    secret = str(cfg['bridge']['secret'])  # pyright: ignore[reportIndexIssue]

    body = body_arg.encode() if body_arg else b''
    ts = int(time.time())
    sig = _sign(secret, method, path, body, ts)

    base = os.environ.get('BRIDGE_URL', 'http://localhost:5050')
    url = f'{base}{path}'
    headers = {'x-bridge-signature': sig}
    if body:
        headers['content-type'] = 'application/json'
        json.loads(body)  # validate; raises if malformed

    with httpx.Client(timeout=10.0) as c:
        r = c.request(method, url, content=body or None, headers=headers)

    print(f'-> {method} {url}')
    print(f'<- {r.status_code}')
    for k, v in r.headers.items():
        print(f'   {k}: {v}')
    print()
    print(r.text)

    return 0 if r.is_success else 1


if __name__ == '__main__':
    sys.exit(main())
