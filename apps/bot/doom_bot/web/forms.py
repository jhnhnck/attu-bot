# SPDX-License-Identifier: Apache-2.0
"""doom_bot.web.forms | form validation models."""

from pydantic import BaseModel, Field, field_validator, model_validator


class GuildChannelsForm(BaseModel):
    """Form validation for guild channels configuration"""

    activity: int = Field(default=0, ge=0)
    announcements: int = Field(default=0, ge=0)
    year_vc: int = Field(default=0, ge=0)
    year_links: int = Field(default=0, ge=0)
    meta_chat: int = Field(default=0, ge=0)
    general: int = Field(default=0, ge=0)
    logs: int = Field(default=0, ge=0)
    eggs: int = Field(default=0, ge=0)
    lore_channels: list[int] = Field(default_factory=list)
    canon_channels: list[int] = Field(default_factory=list)

    @field_validator('lore_channels', 'canon_channels', mode='before')
    @classmethod
    def parse_channel_lists(cls, v):
        """Parse comma-separated channel IDs or lists"""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v


class GuildEpochForm(BaseModel):
    """Form validation for guild epoch configuration"""

    time: int = Field(default=0, ge=0)
    year: int = Field(default=1, ge=1)
    length: int = Field(default=14, ge=1, le=365)
    paused: bool = Field(default=True)
    rollover_minutes: int = Field(default=1020, ge=0, lt=1440)

    @field_validator('rollover_minutes', mode='before')
    @classmethod
    def parse_rollover_time(cls, v):
        """Parse HH:MM format to minutes or accept integer minutes"""
        if isinstance(v, str) and ':' in v:
            try:
                h, m = v.split(':')
                return int(h) * 60 + int(m)
            except (ValueError, IndexError):
                raise ValueError('Invalid time format. Use HH:MM')
        return int(v)


class GuildRolesForm(BaseModel):
    """Form validation for guild roles configuration"""

    announcements: int = Field(default=0, ge=0)
    bot_color: int = Field(default=0, ge=0)
    trees_admin_role: int = Field(default=0, ge=0)
    trees_user_role: int = Field(default=0, ge=0)


class GuildUsersForm(BaseModel):
    """Form validation for guild users configuration"""

    markers: list[int] = Field(default_factory=list)

    @field_validator('markers', mode='before')
    @classmethod
    def parse_user_list(cls, v):
        """Parse comma-separated user IDs or lists"""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v


class GuildStarboardForm(BaseModel):
    """Form validation for guild starboard configuration"""

    channel_id: int = Field(default=0, ge=0)
    emojis: dict[str, str] = Field(default_factory=dict)  # emoji_str -> '#RRGGBB'
    valid_bots: list[int] = Field(default_factory=list)

    @field_validator('emojis', mode='before')
    @classmethod
    def validate_emoji_colors(cls, v):
        """ensure all color values are valid hex strings"""
        import json
        import re

        # serializeForm sends emojis as a JSON-encoded string from the hidden field
        if isinstance(v, str):
            if not v.strip():
                return {}
            try:
                v = json.loads(v)
            except Exception as err:
                raise ValueError(f'emojis could not be parsed as JSON: {err}')
        if not isinstance(v, dict):
            raise ValueError(f'emojis must be a dict, got {type(v).__name__}')
        pattern = re.compile(r'^#[0-9a-fA-F]{6}$')
        for emoji, color in v.items():
            if not pattern.match(color):
                raise ValueError(f'invalid color "{color}" for emoji "{emoji}" - must be #RRGGBB')
        return v

    @field_validator('valid_bots', mode='before')
    @classmethod
    def parse_bot_list(cls, v):
        """parse comma-separated bot IDs or lists"""
        if isinstance(v, str):
            if not v.strip():
                return []
            return [int(x.strip()) for x in v.split(',') if x.strip()]
        return v


class GuildConfigForm(BaseModel):
    """Complete guild configuration form"""

    channels: GuildChannelsForm = Field(default_factory=GuildChannelsForm)
    epoch: GuildEpochForm = Field(default_factory=GuildEpochForm)
    roles: GuildRolesForm = Field(default_factory=GuildRolesForm)
    users: GuildUsersForm = Field(default_factory=GuildUsersForm)
    starboard: GuildStarboardForm = Field(default_factory=GuildStarboardForm)

    @model_validator(mode='before')
    @classmethod
    def flatten_form_data(cls, data):
        """Convert flat form data to nested structure"""
        if not isinstance(data, dict):
            return data

        # Build nested structure, preserving existing nested dictionaries
        result = {
            'channels': data.get('channels', {}).copy() if isinstance(data.get('channels'), dict) else {},
            'epoch': data.get('epoch', {}).copy() if isinstance(data.get('epoch'), dict) else {},
            'roles': data.get('roles', {}).copy() if isinstance(data.get('roles'), dict) else {},
            'users': data.get('users', {}).copy() if isinstance(data.get('users'), dict) else {},
            'starboard': data.get('starboard', {}).copy() if isinstance(data.get('starboard'), dict) else {},
        }

        for key, value in data.items():
            if key in result:
                continue

            if '.' in key:
                section, field = key.split('.', 1)
                if section in result:
                    result[section][field] = value
            # Try to infer section from field name
            elif key in GuildChannelsForm.model_fields:
                result['channels'][key] = value
            elif key in GuildEpochForm.model_fields:
                result['epoch'][key] = value
            elif key in GuildRolesForm.model_fields:
                result['roles'][key] = value
            elif key in GuildUsersForm.model_fields:
                result['users'][key] = value
            elif key in GuildStarboardForm.model_fields:
                result['starboard'][key] = value

        return result


class ThemeConfigForm(BaseModel):
    """Form validation for theme configuration"""

    rotation: float = Field(default=0.0)
    max_rate: float = Field(default=0.5, ge=0.0, le=360.0)
    saturation: float = Field(default=1.0, ge=0.0, le=1.0)
    lightness: float = Field(default=0.5, ge=0.0, le=1.0)
    bot_color: str = Field(default='#ff0000', pattern=r'^#[0-9a-fA-F]{6}$')
    guild_color: str = Field(default='#ffffff', pattern=r'^#[0-9a-fA-F]{6}$')
    logo_rings: str = Field(default='#000000', pattern=r'^#[0-9a-fA-F]{6}$')
    logo_planet: str = Field(default='#000000', pattern=r'^#[0-9a-fA-F]{6}$')
    ui_emojis: dict[str, int] = Field(default_factory=dict)

    @field_validator('ui_emojis', mode='before')
    @classmethod
    def parse_ui_emojis(cls, v):
        """accept JSON string or dict of name -> snowflake id"""
        import json

        if isinstance(v, str):
            if not v.strip():
                return {}
            try:
                v = json.loads(v)
            except Exception as err:
                raise ValueError(f'ui_emojis could not be parsed as JSON: {err}')
        if not isinstance(v, dict):
            raise ValueError(f'ui_emojis must be a dict, got {type(v).__name__}')
        return {str(k): int(val) for k, val in v.items()}


class SystemConfigForm(BaseModel):
    """Form validation for system configuration"""

    primary_guild: int = Field(ge=0)
    error_log_guild: int = Field(default=0, ge=0)
    error_log_channel: int = Field(default=0, ge=0)
    error_hook: str = Field(default='')

    @field_validator('error_hook')
    @classmethod
    def validate_webhook_url(cls, v):
        """Validate Discord webhook URL format"""
        if not v:
            return v
        if not v.startswith('https://discord.com/api/webhooks/'):
            raise ValueError('Must be a valid Discord webhook URL')
        return v

    @model_validator(mode='before')
    @classmethod
    def parse_error_log(cls, data):
        """Handle error_log as [guild, channel] or separate fields"""
        if not isinstance(data, dict):
            return data

        if 'error_log' in data and isinstance(data['error_log'], list):
            if len(data['error_log']) >= 2:
                data['error_log_guild'] = data['error_log'][0]
                data['error_log_channel'] = data['error_log'][1]
            del data['error_log']

        return data
