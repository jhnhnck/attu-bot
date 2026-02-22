"""
AttuBot - Pydantic Models for MongoDB Documents
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict

class GuildConfigDocument(BaseModel):
    """MongoDB document for guild configuration

    Note: epoch dict stores rollover_minutes (int) instead of rollover_time (str)
    for simpler storage and manipulation.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True, extra='ignore')

    guild_id: int
    channels: dict
    epoch: dict
    roles: dict
    users: dict


class ThemeDocument(BaseModel):
    """MongoDB document for theme configuration"""
    model_config = ConfigDict(extra='ignore')

    config_type: Literal['theme'] = 'theme'
    rotation: float
    max_rate: float
    bot_color: str
    guild_color: str


class SystemConfigDocument(BaseModel):
    """MongoDB document for system configuration"""
    model_config = ConfigDict(extra='ignore')

    config_type: Literal['system'] = 'system'
    version: str
    error_log: list[int]  # [guild_id, channel_id]
    error_hook: str
    primary_guild: int


class YearMarkerDocument(BaseModel):
    """MongoDB document for year markers"""
    model_config = ConfigDict(extra='ignore')

    guild: int
    channel: int
    message: int
    year: int
    exact: bool = False
    wiki_page: bool = False


class YearDocument(BaseModel):
    """MongoDB document for year records"""
    model_config = ConfigDict(extra='ignore')

    guild: int
    year: int
    start_time: int
    end_time: int = 0
    duration: int = 0
    formatted: str = ''
    notes: str = ''


class ReloadSignalDocument(BaseModel):
    """MongoDB document for cross-process config reload signals

    written by the web process; consumed and deleted by the bot process.
    upserted by (signal_type, guild_id) so rapid saves coalesce into one signal.
    """
    model_config = ConfigDict(extra='ignore')

    signal_type: Literal['guild', 'theme', 'system']
    guild_id: int | None = None
    timestamp: int = 0

    @classmethod
    def make(cls, signal_type: Literal['guild', 'theme', 'system'], guild_id: int | None = None) -> 'ReloadSignalDocument':
        return cls(signal_type=signal_type, guild_id=guild_id, timestamp=int(time.time()))
