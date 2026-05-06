"""
AttuBot - Chat web form validation models (dormant)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pydantic import BaseModel, Field, field_validator


class ChatChannelConfigForm(BaseModel):
    """Form validation for a single chat channel entry"""

    name: str = Field(default='')
    description: str = Field(default='')
    channel_type: str = Field(default='discussion')
    ingest: bool = Field(default=True)

    @field_validator('channel_type')
    @classmethod
    def validate_channel_type(cls, v):
        """enforce known channel types"""
        valid = {'roleplay', 'discussion', 'shitpost', 'forum'}
        if v not in valid:
            raise ValueError(f'must be one of: {", ".join(sorted(valid))}')
        return v


class ChatConfigForm(BaseModel):
    """Form validation for chat runtime configuration"""

    discord_lookback_hours: int = Field(default=6, ge=1, le=168)
    discord_window_minutes: int = Field(default=30, ge=5, le=720)
    noise_filter_min_tokens: int = Field(default=20, ge=0, le=200)
    ignored_user_ids: list[int] = Field(default_factory=list)
    ingest_discord: bool = Field(default=True)
    ingest_wiki: bool = Field(default=True)
    ingest_documents: bool = Field(default=True)
    wiki_namespaces: list[str] = Field(default_factory=lambda: ['0'])
    character_log_channel_id: int | None = Field(default=None)
    chat_channels: dict[str, ChatChannelConfigForm] = Field(default_factory=dict)
    user_nations: dict[str, str] = Field(default_factory=dict)
    retrieval_top_k_wiki: int = Field(default=5, ge=1, le=20)
    retrieval_top_k_discord: int = Field(default=5, ge=1, le=20)
    retrieval_top_k_documents: int = Field(default=3, ge=1, le=20)
    retrieval_top_k_images: int = Field(default=2, ge=1, le=20)

    @field_validator('ignored_user_ids', mode='before')
    @classmethod
    def parse_user_ids(cls, v):
        """accept comma-separated string or list"""
        if isinstance(v, str):
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v

    @field_validator('wiki_namespaces', mode='before')
    @classmethod
    def parse_namespaces(cls, v):
        """accept comma-separated string or list"""
        if isinstance(v, str):
            return [x.strip() for x in v.split(',') if x.strip()]
        return v

    @field_validator('character_log_channel_id', mode='before')
    @classmethod
    def parse_channel_id(cls, v):
        """treat 0 or empty string as None"""
        if v in {0, ''} or v is None:
            return None
        return int(v)
