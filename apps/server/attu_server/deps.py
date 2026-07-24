# SPDX-License-Identifier: Apache-2.0
"""attu_server.deps | fastapi dependencies (config, storage, bridge client)."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from attu_models.connection import MongoStorage
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig


def get_config(request: Request) -> ServerConfig:
    return request.app.state.config


def get_storage(request: Request) -> MongoStorage:
    return request.app.state.storage


def get_bridge(request: Request) -> BridgeClient:
    return request.app.state.bridge


def require_api_key(
    config: Annotated[ServerConfig, Depends(get_config)],
    request: Request,
) -> None:
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    key = auth.removeprefix('Bearer ')
    if key not in config.auth.api_keys:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
