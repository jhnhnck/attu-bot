# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.features | per-guild feature enable/disable endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status

from attu_models.connection import MongoStorage
from attu_models.repositories import ConfigRepository
from attu_server.api.admin.guilds import _build_guild_slug_map
from attu_server.api.admin.slugs import resolve_guild_id
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config, get_storage


router = APIRouter()

# maps feature names to their actual mongodb field paths in the guild document
_FEATURE_FIELDS: dict[str, str] = {
    'ccboard': 'ccboard.enabled',
    'starboard': 'starboard.enabled',
}

# default enabled state when the field is absent from the document
_FEATURE_DEFAULTS: dict[str, bool] = {
    'ccboard': False,
    'starboard': True,
}


async def _toggle_feature(
    slug: str,
    feature: str,
    enabled: bool,
    config: ServerConfig,
    bridge: BridgeClient,
    storage: MongoStorage,
) -> dict[str, Any]:
    """load guild config, set the feature's enabled field, save, and notify bridge."""
    if feature not in _FEATURE_FIELDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f'unknown feature {feature!r}; valid: {", ".join(_FEATURE_FIELDS)}',
        )

    slug_map = await _build_guild_slug_map(config, bridge)
    guild_id = resolve_guild_id(slug, slug_map)
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')

    repo = ConfigRepository(storage.get_db())
    doc = await repo.get_guild(guild_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild config not found')

    await repo.update_guild_field(guild_id, _FEATURE_FIELDS[feature], enabled)
    await bridge.invalidate_guild_cache(guild_id)
    await bridge.trigger_reload('guild', guild_id)

    return {'feature': feature, 'enabled': enabled}


@router.get('/guilds/{slug}/features')
async def list_features(
    slug: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
    storage: Annotated[MongoStorage, Depends(get_storage)],
) -> dict[str, Any]:
    slug_map = await _build_guild_slug_map(config, bridge)
    guild_id = resolve_guild_id(slug, slug_map)
    if guild_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild not found')

    repo = ConfigRepository(storage.get_db())
    doc = await repo.get_guild(guild_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='guild config not found')

    features = []
    for name, default in _FEATURE_DEFAULTS.items():
        subdoc = getattr(doc, name, {})
        if isinstance(subdoc, dict):
            enabled = subdoc.get('enabled', default)
        else:
            enabled = default
        features.append({'name': name, 'enabled': bool(enabled)})

    return {'features': features}


@router.post('/guilds/{slug}/features/{feature}/enable')
async def enable_feature(
    slug: str,
    feature: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
    storage: Annotated[MongoStorage, Depends(get_storage)],
) -> dict[str, Any]:
    return await _toggle_feature(slug, feature, True, config, bridge, storage)


@router.post('/guilds/{slug}/features/{feature}/disable')
async def disable_feature(
    slug: str,
    feature: str,
    config: Annotated[ServerConfig, Depends(get_config)],
    bridge: Annotated[BridgeClient, Depends(get_bridge)],
    storage: Annotated[MongoStorage, Depends(get_storage)],
) -> dict[str, Any]:
    return await _toggle_feature(slug, feature, False, config, bridge, storage)
