"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
import types
from datetime import time
from os import getenv
from pathlib import Path
from types import SimpleNamespace
from typing import ClassVar
from zoneinfo import ZoneInfo

import toml
from pydantic import BaseModel, ValidationError, model_validator
from tortoise import Tortoise, fields
from tortoise.models import Model

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Database Model ---

class NovaToken(Model):
    id = fields.IntField(primary_key=True)
    guild = fields.IntField(default=0)
    key = fields.TextField()
    value = fields.TextField(default='X = 0')

    async def pack(self, value):
        self.value = toml.dumps({'X': value})
        await self.save()

    def unpack(self):
        return toml.loads(self.value)['X']

    def __str__(self):
        return f'{self.guild}/{self.key}={self.unpack()}'

# --- Components ---

class WikiAuth(BaseModel):
    key: str
    page: str
    user: str
    endpoint: str

class GuildChannels(BaseModel):
    pass

class GuildEpoch(BaseModel):
    pass

class GuildRoles(BaseModel):
    pass

class Guild(BaseModel):
    channels: GuildChannels
    epoch: GuildEpoch
    channels: GuildRoles
    markers: list[int]

# --- Exceptions ---

class UnauthorizedGuild(Exception):
    def __init__(self, guild):
        self.message = f'Guild "{guild}" not in the authorized guilds list'
        super().__init__(self.message)


# --- Config Class ---

# New Config Rewrite
class NovaConfig:
    config_version = __version__

    # Dynamic Attributes
    path = Path(getenv('ATTU_CONFIG_FILE', './attu-bot.toml')).resolve()
    db_path = Path(getenv('ATTU_MARKER_DB', './markers.db')).resolve()
    _bot: ClassVar = None
    _guilds: ClassVar[dict[str, Guild]] = {}

    @classmethod  # called first upon startup, load config file only
    def on_init(cls):
        logger.info('Bootstrapping config loading process')

        if not cls.path.exists():
            logger.error('Config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{cls.path}"')

        with cls.path.open() as file:
            cls._raw = toml.load(file)

        # validate config version
        if cls._raw['config_version'] != cls.config_version:
            logger.fatal('Incompatible config version!')
            sys.exit(1)
        else:
            logger.info(f'Matched file version: {__version__}')

        # --- Unpack into Attributes ---

        # Auth
        cls.bot_token = cls._raw['auth']['bot']['token']
        cls.authorized_guilds = cls._raw['discord']['guilds']['authorized']

        try:
            cls.wiki = WikiAuth(**cls._raw['auth']['wiki'])

        except ValidationError as err:
            for line in err.errors():
                logger.fatal(f'Validation Failed: {line.type} {line.loc!s} {line.msg}')

            sys.exit(1)

    @classmethod  # called by Bot.on_ready after connect, low priority maintainence tasks
    async def on_ready(cls, bot):
        cls._bot = bot

        if bot.user.id not in Config.users.markers:
            logger.info('Adding bot user to valid year marker authors')
            Config.users.markers.append(bot.user.id)

        cls.path.chmod(0o660)
        cls.db_path.chmod(0o660)

        # dump keys with empty values
        await NovaToken.filter(value='X = 0').delete()

        await Tortoise.close_connections()

    @classmethod  # called by markers setup after db is connected
    async def on_load(cls):
        # handle data migration
        if cls.config_version != (await cls._get('version', default=cls.config_version)):
            await cls._migrate()
        else:
            logger.info(f'Matched table version: {__version__}')

    # --- Debug ---

    # TODO: Move this below Pivate Methods
    @classmethod
    def to_dict(cls):
        result = {}

        def convert_value(value):
            if isinstance(value, SimpleNamespace | BaseModel):
                return {k: convert_value(v) for k, v in vars(value).items()}

            elif isinstance(value, list):
                return [convert_value(item) for item in value]

            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}

            else:
                return value

        for attr_name in vars(cls):
            if attr_name.startswith('_'):
                continue

            attr_value = getattr(cls, attr_name)
            if isinstance(attr_value, types.MethodType | types.FunctionType):
                continue

            result[attr_name] = convert_value(attr_value)
        return result

    # --- Public Methods ---

    @classmethod
    def guild(cls, guild):
        if guild in cls.authorized_guilds:
            return cls._guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    # --- Private Methods ---

    @staticmethod
    async def _get(key: str, guild: int = 0, default = None):
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created:
            logger.warn(f'Key Missing [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        return token.unpack()

    @staticmethod
    async def _set(key: str, value, guild: int = 0):
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        logger.warn(f'Key {"Created" if created else "Changed"} [{guild}/{key.lower()}] old={token.unpack()} new={value}')
        await key.pack(value)

    @classmethod
    async def _migrate(cls):
        version = await cls._get('version')

        logger.info(f'Beginning config table migration from "{version}"')

        # re-check at end of migration
        if cls.config_version != (await cls._get('version')):
            logger.fatal(f'Failed to migrate config table! Got to {await cls._get("version")}')
            sys.exit(1)

# Old Methods and Layout
class Config:
    config_version = NovaConfig.config_version
    path = NovaConfig.path
    db_path = NovaConfig.db_path

    @staticmethod
    def init():
        NovaConfig.on_init()  # bootstrap load
        Config._raw = NovaConfig._raw

        # --- Unpack into Attributes ---

        Config.bot_token = Config._raw['auth']['bot']['token']

        Config.wiki_key = NovaConfig.wiki.key
        Config.wiki_page = NovaConfig.wiki.page
        Config.wiki_user = NovaConfig.wiki.user
        Config.wiki_endpoint = NovaConfig.wiki.endpoint

        # Users
        Config.users = SimpleNamespace(
            markers = Config._raw['discord']['users']['markers'],
        )

        # Channels
        Config.activity_channel = Config._raw['discord']['channels']['activity']
        Config.year_vc = Config._raw['discord']['channels']['year_vc']
        Config.announce_channel = Config._raw['discord']['channels']['announcements']
        Config.doom_forum = Config._raw['discord']['channels']['doom_forum']
        Config.year_link_thread = Config._raw['discord']['channels']['year_links']
        Config.meta_chat_channel = Config._raw['discord']['channels']['meta_chat']
        Config.error_log_channel = Config._raw['discord']['channels']['error_log']
        Config.lore_channels = Config._raw['discord']['channels']['lore_channels']

        # Roles
        Config.announce_role = Config._raw['discord']['roles']['leaders']

        # Guilds
        Config.authorized_guilds = list(Config._raw['discord']['guilds'].values())
        Config.attu_guild = Config._raw['discord']['guilds']['attu']
        Config.jhn_guild = Config._raw['discord']['guilds']['jhn']

        # Epoch
        Config.epoch_time = Config._raw['epoch']['time']
        Config.epoch_year = Config._raw['epoch']['year']
        Config.epoch_length = Config._raw['epoch']['length']
        Config.time_paused = Config._raw['epoch']['paused']

        th = Config._raw['epoch']['rollover_time'].split(':')
        Config.rollover_time = time(int(th[0]), int(th[1]), tzinfo=ZoneInfo(getenv('TZ')))

        # Timestamps optional (still present for bootstrapping bot if needed for now)
        Config.timestamps = Config._raw.get('timestamps', [])

        Config.to_dict = NovaConfig.to_dict

    @staticmethod
    def _save():
        logger.info(f'Writing new config to "{Config.path}"')

        with Config.path.open('w') as file:
            toml.dump(Config._raw, file)

        Config._load()

    # --- Public Methods ---

    @staticmethod
    def set_epoch(time, year: int):
        logger.warn(f'Epoch changed: old={Config.epoch_time},{Config.epoch_year} new={int(time)},{year}')

        Config._raw['epoch']['time'] = int(time)
        Config._raw['epoch']['year'] = year
        Config._save()

    @staticmethod
    def set_epoch_length(length: int):
        logger.warn(f'Epoch length changed: old={Config.epoch_length} new={length}')

        Config._raw['epoch']['length'] = length
        Config._save()

    @staticmethod
    def pause_time():
        logger.warn(f'Epoch pause changed: old={Config.time_paused} new=True')

        Config._raw['epoch']['paused'] = True
        Config._save()

    @staticmethod
    def resume_time():
        logger.warn(f'Epoch pause changed: old={Config.time_paused} new=False')

        Config._raw['epoch']['paused'] = False
        Config._save()
