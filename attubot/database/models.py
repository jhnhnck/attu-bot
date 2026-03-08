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
    starboard: dict = {}


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
    notes: str = ''


class MessageAuthor(BaseModel):
    """Author info snapshot embedded in a MessageDocument"""

    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    bot: bool = False


class MessageContent(BaseModel):
    """Message body and media embedded in a MessageDocument"""

    model_config = ConfigDict(extra='ignore')

    text: str = ''
    attachments: list[dict] = []  # [{filename, url, content_type, size, saved_path}]
    embeds: list[dict] = []
    sticker_ids: list[int] = []
    forwarded: bool = False  # true when content was extracted from message.snapshots


class MessageRefs(BaseModel):
    """Cross-references to other messages embedded in a MessageDocument"""

    model_config = ConfigDict(extra='ignore')

    reply_to: int | None = None  # reply-to message id (was: reference_id)
    starboard_post: int | None = None  # linked starboard post id (was: starboard_reference_id)


class MessageDocument(BaseModel):
    """MongoDB document for a stored Discord message"""

    model_config = ConfigDict(extra='ignore')

    message_id: int
    guild_id: int
    channel_id: int  # thread id if in a thread
    parent_channel_id: int | None = None  # set only when channel_id is a thread
    author: MessageAuthor
    content: MessageContent = MessageContent()
    refs: MessageRefs = MessageRefs()
    pinned: bool = False
    public: bool = True  # readable by @everyone
    created_at: int  # unix timestamp
    edited_at: int | None = None
    deleted: bool = False
    deleted_at: int | None = None


class StarredMessageDocument(BaseModel):
    """MongoDB document tracking stars earned by a message"""

    model_config = ConfigDict(extra='ignore')

    message_id: int
    channel_id: int
    guild_id: int
    author_id: int
    starboard_message_id: int | None = None  # post in the starboard channel, if any
    reactions: dict[str, list[int]] = {}  # emoji_str -> list of user_ids who normal-reacted
    super_reactions: dict[str, list[int]] = {}  # emoji_str -> list of user_ids who super-reacted (1.5x weight)
    total_reactions: int = 0  # raw count of all reactors (normal + super); kept for range queries
    weighted_total: float = 0.0  # weighted sum: normal = 1.0, super = 1.5


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
