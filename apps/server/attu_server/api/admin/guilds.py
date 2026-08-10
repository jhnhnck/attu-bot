# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.guilds | guild listing endpoints."""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from attu_server.api.admin.slugs import make_slug_map
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config


router = APIRouter()


async def _build_guild_slug_map(config: ServerConfig, bridge: BridgeClient) -> dict[str, dict[str, Any]]:
    """fetch guild info for all configured guilds and return slug -> {id, name, role} map."""
    infos = await asyncio.gather(*[bridge.get_guild_info(g.id) for g in config.guilds])
    items = [{'id': info['id'], 'name': info['name'], 'role': g.role} for g, info in zip(config.guilds, infos)]
    return make_slug_map(items)


@router.get('/guilds')
async def list_guilds(
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> list[dict[str, Any]]:
    slug_map = await _build_guild_slug_map(config, bridge)
    return [{'id': item['id'], 'name': item['name'], 'slug': slug, 'role': item['role']} for slug, item in slug_map.items()]


@router.get('/guilds/{slug}/channels')
async def list_guild_channels(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> list[dict[str, Any]]:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild = slug_map.get(slug)
    if guild is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')
    channels = await bridge.get_guild_channels(int(guild['id']))
    channel_slug_map = make_slug_map(channels)
    return [{'id': item['id'], 'name': item['name'], 'slug': s, 'type': item['type']} for s, item in channel_slug_map.items()]


@router.get('/guilds/{slug}/roles')
async def list_guild_roles(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
) -> list[dict[str, Any]]:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild = slug_map.get(slug)
    if guild is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')
    roles = await bridge.get_guild_roles(int(guild['id']))
    role_slug_map = make_slug_map(roles)
    return [{'id': item['id'], 'name': item['name'], 'slug': s} for s, item in role_slug_map.items()]
