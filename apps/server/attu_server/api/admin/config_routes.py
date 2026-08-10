# SPDX-License-Identifier: Apache-2.0
"""attu_server.api.admin.config_routes | guild config get/set via dot-path key."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from attu_models.connection import MongoStorage
from attu_models.documents import GuildConfigDocument
from attu_models.repositories import ConfigRepository
from attu_server.api.admin.guilds import _build_guild_slug_map
from attu_server.api.admin.slugs import make_slug_map, resolve_guild_id
from attu_server.bridge_client import BridgeClient
from attu_server.config import ServerConfig
from attu_server.deps import get_bridge, get_config, get_storage


router = APIRouter()

# terminal field name suffixes that trigger channel/role slug resolution
_CHANNEL_SUFFIXES = ('_channel', '_id')
_ROLE_SUFFIXES = ('_role',)


async def _resolve_snowflake(terminal: str, raw_value: Any, guild_id: int, bridge: BridgeClient) -> Any:
    """resolve a channel/role slug to an integer snowflake when the terminal key suggests one.

    if the terminal field name doesn't end with a known suffix, returns raw_value unchanged.
    if it does, attempts slug lookup first, then int coercion, raising 422 on failure.
    """
    is_role = any(terminal.endswith(suf) for suf in _ROLE_SUFFIXES)
    is_channel = not is_role and any(terminal.endswith(suf) for suf in _CHANNEL_SUFFIXES)
    if not (is_role or is_channel):
        return raw_value

    items = await (bridge.get_guild_roles(guild_id) if is_role else bridge.get_guild_channels(guild_id))
    item_map = make_slug_map(items)

    if isinstance(raw_value, int):
        return raw_value
    if not isinstance(raw_value, str):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'expected string slug or integer for {terminal!r}')
    match = item_map.get(raw_value)
    if match is not None:
        return int(match['id'])
    try:
        return int(raw_value)
    except (ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'{raw_value!r} is not a valid slug or integer snowflake')


def _traverse(doc: GuildConfigDocument, segments: list[str]) -> Any:
    """walk dot-path segments on a GuildConfigDocument.

    checks model_fields at each BaseModel level; dict keys are an open key space.
    raises 422 if a model-level segment name is not in model_fields.
    note: GuildConfigDocument sub-fields (channels, epoch, roles, etc.) are all plain
    dicts, so model_fields validation only binds at depth 1 (the top-level document).
    """
    current: Any = doc
    for seg in segments:
        if isinstance(current, BaseModel):
            if not hasattr(current, seg) or seg not in current.model_fields:
                raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'unknown key: {seg!r}')
            current = getattr(current, seg)
        elif isinstance(current, dict):
            current = current.get(seg)
        else:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'cannot traverse into {type(current).__name__} at {seg!r}')
    return current


class ConfigPatch(BaseModel):
    value: Any


@router.get('/guilds/{slug}/config/{key}')
async def get_guild_config(
    slug: str,
    key: str,
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

    segments = key.split('.')
    value = _traverse(doc, segments)
    return {'key': key, 'value': value}


@router.patch('/guilds/{slug}/config/{key}')
async def patch_guild_config(
    slug: str,
    key: str,
    body: ConfigPatch,
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

    segments = key.split('.')
    terminal = segments[-1]

    # validate path against model_fields (raises 422 on unknown top-level key)
    _traverse(doc, segments)

    # resolve channel/role slug to integer snowflake when the terminal key suggests one
    resolved: Any = await _resolve_snowflake(terminal, body.value, guild_id, bridge)

    # reconstruct doc data without mutating the existing doc
    doc_data = doc.model_dump()
    node = doc_data
    for seg in segments[:-1]:
        if not isinstance(node, dict):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f'cannot traverse: {seg!r}')
        node = node.setdefault(seg, {})
    node[segments[-1]] = resolved

    try:
        GuildConfigDocument.model_validate(doc_data)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await repo.update_guild_field(guild_id, key, resolved)
    await bridge.invalidate_guild_cache(guild_id)
    await bridge.trigger_reload('guild', guild_id)

    return {'key': key, 'value': resolved}
