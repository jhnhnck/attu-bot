# SPDX-License-Identifier: Apache-2.0
"""attu_server.deps | fastapi dependencies (config, storage, bridge client)."""

from fastapi import Request

from attu_models.connection import MongoStorage
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig


def get_config(request: Request) -> ServerConfig:
    return request.app.state.config


def get_storage(request: Request) -> MongoStorage:
    return request.app.state.storage


def get_bridge(request: Request) -> BridgeClient:
    return request.app.state.bridge
