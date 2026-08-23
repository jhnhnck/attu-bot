# SPDX-License-Identifier: Apache-2.0
"""attu_models.documents | pydantic models for MongoDB documents."""

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict


class GuildConfigDocument(BaseModel):
    """MongoDB document for guild configuration."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra='ignore')

    guild_id: int
    channels: dict
    epoch: dict
    roles: dict
    users: dict
    starboard: dict = {}
    ccboard: dict = {}
    features: dict = {}


class ThemeDocument(BaseModel):
    """MongoDB document for theme configuration."""

    model_config = ConfigDict(extra='ignore')

    config_type: Literal['theme'] = 'theme'
    rotation: float
    max_rate: float
    bot_color: str
    guild_color: str
    logo_rings: str = '#000000'
    logo_planet: str = '#000000'
    saturation: float = 1.0
    lightness: float = 0.5
    egg_emojis: dict[str, int] = {}
    progress_emojis: dict[str, int] = {}
    ui_emojis: dict[str, int] = {}


class SystemConfigDocument(BaseModel):
    """MongoDB document for system configuration."""

    model_config = ConfigDict(extra='ignore')

    config_type: Literal['system'] = 'system'
    version: str
    error_log: list[int]  # [guild_id, channel_id]
    error_hook: str
    primary_guild: int


class YearMarkerDocument(BaseModel):
    """MongoDB document for year markers."""

    model_config = ConfigDict(extra='ignore')

    guild: int
    channel: int
    message: int
    year: int
    exact: bool = False
    wiki_page: bool = False


class YearDocument(BaseModel):
    """MongoDB document for year records."""

    model_config = ConfigDict(extra='ignore')

    guild: int
    year: int
    start_time: int
    end_time: int = 0
    duration: int = 0
    notes: str = ''


class MessageAuthor(BaseModel):
    """author info snapshot embedded in a MessageDocument."""

    model_config = ConfigDict(extra='ignore')

    id: int
    name: str
    bot: bool = False


class MessageContent(BaseModel):
    """message body and media embedded in a MessageDocument."""

    model_config = ConfigDict(extra='ignore')

    text: str = ''
    attachments: list[dict] = []  # [{filename, url, content_type, size, saved_path}]
    embeds: list[dict] = []
    sticker_ids: list[int] = []
    sticker_urls: list[str] = []  # resolved cdn urls for attached stickers
    poll_text: str | None = None  # human-readable poll serialization (question, options, results)
    forwarded: bool = False  # true when content was extracted from message.snapshots


class MessageRefs(BaseModel):
    """cross-references to other messages embedded in a MessageDocument."""

    model_config = ConfigDict(extra='ignore')

    reply_to: int | None = None  # reply-to message id (was: reference_id)
    starboard_post: int | None = None  # linked starboard post id (was: starboard_reference_id)


class MessageDocument(BaseModel):
    """MongoDB document for a stored Discord message."""

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


class ReloadSignalDocument(BaseModel):
    """MongoDB document for cross-process config reload signals.

    written by the web process; consumed and deleted by a target consumer process.
    upserted by (target, signal_type, guild_id) so rapid saves coalesce per target.
    """

    model_config = ConfigDict(extra='ignore')

    signal_type: Literal['guild', 'theme', 'system']
    guild_id: int | None = None
    timestamp: int = 0
    target: Literal['bot', 'ingestor'] = 'bot'

    @classmethod
    def make(
        cls,
        signal_type: Literal['guild', 'theme', 'system'],
        guild_id: int | None = None,
        target: Literal['bot', 'ingestor'] = 'bot',
    ) -> 'ReloadSignalDocument':
        return cls(signal_type=signal_type, guild_id=guild_id, timestamp=int(time.time()), target=target)
