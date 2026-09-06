# SPDX-License-Identifier: Apache-2.0
"""attu_server.config | server-side TOML loader; reuses attu-bot.toml."""

import os
from pathlib import Path
from typing import Any, cast

import tomlkit
from pydantic import BaseModel, ValidationError


class DatabaseConfig(BaseModel):
    url: str
    name: str


class BridgeConfig(BaseModel):
    secret: str
    bot_url: str = 'http://core:5050'  # compose service name; overridable per env
    replay_window: int = 60
    request_timeout: float = 10.0


class GuildEntry(BaseModel):
    id: int
    role: str


class AuthConfig(BaseModel):
    """attu-server auth material; reads [auth.server] in the shared toml."""

    # bearer tokens accepted by the admin api
    api_keys: list[str] = []
    # session cookie signing key
    secret_key: str


class ServerConfig(BaseModel):
    database: DatabaseConfig
    bridge: BridgeConfig
    auth: AuthConfig
    guilds: list[GuildEntry] = []


class ServerConfigError(Exception):
    pass


def load_config(path: Path | None = None) -> ServerConfig:
    """load + validate the shared attu-bot.toml from disk."""
    p = path or Path(os.environ.get('ATTU_CONFIG_FILE', './.secrets/attu-bot.toml')).resolve()
    if not p.exists():
        raise ServerConfigError(f'config file not found: {p}')

    with p.open() as f:
        raw = cast(dict[str, Any], tomlkit.load(f))

    try:
        return ServerConfig(
            database=DatabaseConfig(**raw['database']),
            bridge=BridgeConfig(**raw['bridge']),
            auth=AuthConfig(**raw['auth']['server']),
            guilds=[GuildEntry(**g) for g in raw.get('guilds', [])],
        )
    except (KeyError, ValidationError) as e:
        raise ServerConfigError(f'invalid config: {e!s}') from e
