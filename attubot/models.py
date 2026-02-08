"""
AttuBot - Pydantic Models for MongoDB Documents
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from typing import Literal

from pydantic import BaseModel

class GuildConfigDocument(BaseModel):
    """MongoDB document for guild configuration

    Note: epoch dict stores rollover_minutes (int) instead of rollover_time (str)
    for simpler storage and manipulation.
    """
    guild_id: int
    channels: dict
    epoch: dict
    roles: dict
    users: dict

    class Config:
        arbitrary_types_allowed = True
        extra = 'ignore'  # Ignore unknown fields for expandability


class ThemeDocument(BaseModel):
    """MongoDB document for theme configuration"""
    config_type: Literal['theme'] = 'theme'
    rotation: float
    max_rate: float
    bot_color: str
    guild_color: str

    class Config:
        extra = 'ignore'


class SystemConfigDocument(BaseModel):
    """MongoDB document for system configuration"""
    config_type: Literal['system'] = 'system'
    version: str
    error_log: list[int]  # [guild_id, channel_id]
    error_hook: str
    primary_guild: int

    class Config:
        extra = 'ignore'


class YearMarkerDocument(BaseModel):
    """MongoDB document for year markers"""
    channel: int
    message: int
    year: int
    exact: bool = False
    wiki_page: bool = False

    class Config:
        extra = 'ignore'
