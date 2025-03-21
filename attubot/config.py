"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import datetime
import re
import sys
from os import environ, getenv
from pathlib import Path
from typing import ClassVar
from zoneinfo import ZoneInfo

import tomlkit
from pydantic import BaseModel, ValidationError, model_validator
from tortoise import Tortoise, fields
from tortoise.models import Model

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Database Model ---

class NovaToken(Model):
    """
    NovaToken - Key-Value Wrapper for Database

    Args:
      guild (int): snowflake id for discord guild (0 for global)
      key (str): dot-seperated identifier for value (must be in valid)
      value (str): TOML-encoded value (to avoid needing to parse values ourselves)
    """

    id = fields.IntField(primary_key=True)
    guild = fields.IntField(default=0)
    key = fields.TextField()
    value = fields.TextField(default='X = 0')
    # valid_types = []

    async def pack(self, value):
        self.value = tomlkit.dumps({'X': value})
        await self.save()

    def unpack(self):
        return tomlkit.loads(self.value)['X']

    def __str__(self):
        return f'{self.guild}/{self.key}={self.unpack()}'


class ParsedTokenKey(BaseModel):
    guild: int
    key: str

    @model_validator(mode='before')
    def setup(data: dict):
        raw_key = data.get('key', '').lower()
        match = re.fullmatch(r'(?:(\d+)(?:/))?([a-z._]+)', raw_key)

        if match is None:
            raise InvalidTokenKey(raw_key)

        guild, key = match.groups()[0], match.groups()[1]

        if guild is not None:
            data['guild'] = guild

        data['key'] = key

        return data

    @model_validator(mode='after')
    def validate(self):
        if self.guild != 0 and self.guild not in NovaConfig.authorized_guilds:
            raise UnauthorizedGuild(self.guild)

        if (self.guild == 0 and self.key not in NovaConfig.global_keys) or (self.guild != 0 and self.key not in NovaConfig.guild_keys):
            raise InvalidTokenKey(self.key)

        return self

    def authorized(self, user: int, guild: int, mode: str):  # (Keeping mode level here for future usecases)
        return (self.guild == 0 and NovaConfig._bot.is_owner(user)) or self.guild == guild


# --- Components ---

# Could be in the database, but unneeded currently
class WikiAuth(BaseModel):
    key: str
    page: str
    user: str
    endpoint: str


class GuildChannels(BaseModel):
    activity: int
    year_vc: int
    announcements: int
    year_links: int
    meta_chat: int
    lore_channels: list[int]

    @model_validator(mode='before')
    def setup(data: dict):
        data['activity'] = data.get('channels.activity', 0)
        data['year_vc'] = data.get('channels.year_vc', 0)
        data['announcements'] = data.get('channels.announcements', 0)
        data['year_links'] = data.get('channels.year_links', 0)
        data['meta_chat'] = data.get('channels.meta_chat', 0)
        data['lore_channels'] = data.get('channels.lore_channels', [])

        return data


class GuildEpoch(BaseModel):
    time: int  # TODO: Can we unify all stored dates under one class?
    year: int
    length: int
    paused: bool
    rollover_time: datetime.time

    @model_validator(mode='before')
    def setup(data: dict):
        data['time'] = data.get('epoch.time', 0)
        data['year'] = data.get('epoch.year', 1)
        data['length'] = data.get('epoch.length', 14)
        data['paused'] = data.get('epoch.paused', True)

        th = data.get('epoch.rollover_time', '17:00').split(':')
        data['rollover_time'] = datetime.time(int(th[0]), int(th[1]), tzinfo=ZoneInfo(getenv('TZ')))

        return data


class GuildRoles(BaseModel):
    announcements: int

    @model_validator(mode='before')
    def setup(data: dict):
        data['announcements'] = data.get('roles.announcements', 0)

        return data


class GuildUsers(BaseModel):
    markers: list[int]

    @model_validator(mode='before')
    def setup(data: dict):
        data['markers'] = data.get('users.markers', [])

        return data


class Guild(BaseModel):
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    id: int

    @model_validator(mode='before')
    def setup(data: dict):
        data['channels'] = GuildChannels(**data)
        data['epoch'] = GuildEpoch(**data)
        data['roles'] = GuildRoles(**data)
        data['users'] = GuildUsers(**data)

        return data

    async def set_epoch(self, time, year: int):
        logger.warn(f'[{self.id}] Epoch changed: old={self.epoch.time},{self.epoch.year} new={int(time)},{year}')
        self.epoch.time = await NovaConfig.set('epoch.year', int(time), guild=self.id)
        self.epoch.year = await NovaConfig.set('epoch.year', year, guild=self.id)

    async def set_year_length(self, length: int):
        logger.warn(f'[{self.id}] Epoch length changed: old={self.epoch.length} new={length}')
        self.epoch.length = await NovaConfig.set('epoch.length', length, guild=self.id)

    async def pause_time(self):
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=True')
        self.epoch.paused = await NovaConfig.set('epoch.paused', True, guild=self.id)

    async def resume_time(self):
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=False')
        self.epoch.paused = await NovaConfig.set('epoch.paused', False, guild=self.id)

# --- Exceptions ---

class UnauthorizedGuild(Exception):
    def __init__(self, guild):
        self.message = f'Guild "{guild}" not in the authorized guilds list'
        super().__init__(self.message)


class InvalidTokenKey(Exception):
    def __init__(self, key: str):
        self.message = f'Invalid key "{key}" for selected guild or group'
        super().__init__(self.message)

# --- Config Class ---

# New Config Rewrite
class NovaConfig:
    """
    NovaConfig - Redesigned Config Storage System

    design decisions tl;dr
    - only stored in config file for security reasons or if needed before db init step
    - split into three loading steps:
      - on_init: ran first upon start, loads and unpacks config file
      - on_load: ran after database connect, loads and unpacks NovaToken store
      - on_ready: ran after all other init steps, maintainance tasks
    """

    config_version: str = __version__
    wiki: WikiAuth
    bot_token: str
    authorized_guilds: list[int]
    error_log: list[int, int]
    primary_guild: int

    # SELECT DISTINCT key FROM novatoken;
    guild_keys: ClassVar[list[str]] = [
        'channels.activity',
        'channels.announcements',
        'channels.lore_channels',
        'channels.meta_chat',
        'channels.year_links',
        'channels.year_vc',
        'epoch.length',
        'epoch.paused',
        'epoch.rollover_time',
        'epoch.time',
        'epoch.year',
        'roles.announcements',
        'users.markers',
    ]

    global_keys: ClassVar[list[str]] = [
        'error_log',
        'version',
    ]

    valid_keys: ClassVar[list[str]] = [*guild_keys, *global_keys]

    # Dynamic Attributes
    path = Path(getenv('ATTU_CONFIG_FILE', './attu-bot.toml')).resolve()
    db_path = Path(getenv('ATTU_MARKER_DB', './markers.db')).resolve()
    _bot: ClassVar = None
    _guilds: ClassVar[dict[str, Guild]] = {}
    test_mode: bool = 'TEST_MODE' in environ

    @classmethod  # called first upon startup, load config file only
    def on_init(cls):
        logger.info('Bootstrapping config loading process')

        if not cls.path.exists():
            logger.error('Config file missing!')
            sys.exit(1)  # TODO: Throw error instead

        logger.info(f'Loading config from "{cls.path}"')

        with cls.path.open() as file:
            cls._raw = tomlkit.load(file)

        # validate config version
        if cls._raw['config_version'] != cls.config_version:
            logger.fatal('Incompatible config version!')
            sys.exit(1)  # TODO: Throw error instead
        else:
            logger.info(f'Matched file version: {__version__}')

        # unpack into attributes
        cls.bot_token = cls._raw['auth']['bot']['token']
        cls.authorized_guilds = cls._raw['discord']['guilds']['authorized']
        cls.primary_guild = cls._raw['discord']['guilds']['primary']

        try:
            cls.wiki = WikiAuth(**cls._raw['auth']['wiki'])

        except ValidationError as err:
            for line in err.errors():
                logger.error(*[f'Validation failed: {line.loc!s} {line.msg}' for line in err.errors()])
            sys.exit(1)  # TODO: Throw error instead

        Config.on_init()  # bootstrap old config structure

    @classmethod  # called by markers setup after db is connected
    async def on_load(cls):
        # handle data migration
        if cls.config_version != (await cls.get('version', default=cls.config_version)):
            await cls._migrate()
        else:
            logger.info(f'Matched table version: {__version__}')

        # global vars
        cls.error_log: list[int, int] = await cls.get('error_log', default=(0, 0))

        # load guild configs
        for guild in cls.authorized_guilds:
            logger.info(f'Loading guild config for {guild}')
            config = {}

            try:
                async for token in NovaToken.filter(guild=guild):
                    config[str(token.key)] = token.unpack()

                cls._guilds[guild] = Guild(**config, id=guild)

            except ValidationError as err:
                logger.error(*[f'Failed to validate {guild}: {line.loc!s} {line.msg}' for line in err.errors()])

                cls._guilds[guild] = None

        await Tortoise.close_connections()

        Config.on_load()  # bootstrap old config structure

    @classmethod  # called by Bot.on_ready after connect, low priority maintainence tasks
    async def on_ready(cls, bot):
        cls._bot = bot

        if bot.user.id not in Config.users.markers:
            logger.info('Adding bot user to valid year marker authors')
            Config.users.markers.append(bot.user.id)

        for idx, guild in cls._guilds.items():
            if bot.user.id not in guild.users.markers:
                logger.info(f'Adding bot user to valid year marker authors for {idx}')

                guild.users.markers.append(bot.user.id)
                await cls.set('users.markers', guild.users.markers, guild=idx)

        cls.path.chmod(0o660)
        cls.db_path.chmod(0o660)

        # dump keys with empty values
        await NovaToken.filter(value='X = 0').delete()

        if cls.test_mode:
            logger.debug('Dumping NovaConfig:', tomlkit.dumps(NovaConfig.to_dict(), sort_keys=True), sep='\n')

        await Tortoise.close_connections()

    # --- Public Methods ---

    @classmethod
    def parse_key(cls, guild: int, key: str) -> ParsedTokenKey | None:
        try:
            return ParsedTokenKey(guild=guild, key=key)

        except Exception as err:
            logger.error(f'Caught exception in parse_key(): {err!s}')

            return None

    @classmethod
    def guild(cls, guild) -> Guild:
        if guild in cls.authorized_guilds:
            return cls._guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    @staticmethod
    async def get(key: str, guild: int = 0, default=None):
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        return token.unpack()

    @staticmethod
    async def set(key: str, value, guild: int = 0):
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        logger.debug(f'Key {"Created" if created else "Changed"} [{guild}/{key.lower()}] old={token.unpack()} new={value}')
        await token.pack(value)

        return value  # condenses update methods

    @staticmethod
    async def delete(key: str, guild: int = 0):
        token = await NovaToken.get_or_none(guild=guild, key=key.lower())

        if token is not None:
            logger.debug(f'Key Removed [{guild}/{key.lower()}] value={token.unpack()}')
            await token.delete()
        else:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}]; Cannot Remove')

    @classmethod
    def is_owner(cls, user: str):
        return cls._bot.is_owner(user)

    # --- Private Methods ---

    @classmethod
    async def _migrate(cls):
        version = await cls.get('version')

        logger.info(f'Beginning config table migration from "{version}"')
        from attubot.migrations import migration_table

        for migration in migration_table:
            await migration(version)
            version = await cls.get('version')

        # re-check at end of migration
        if cls.config_version != version:
            logger.fatal(f'Failed to migrate config table! Got to {await cls.get("version")}')
            sys.exit(1)  # TODO: Throw error instead
        else:
            logger.info('Finished applying config table patches')

    # --- Debug ---

    @classmethod
    def to_dict(cls):
        result = {}

        def convert_value(value):
            if isinstance(value, BaseModel):
                return {k: convert_value(v) for k, v in vars(value).items()}

            elif isinstance(value, list):
                return [convert_value(item) for item in value]

            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}

            elif isinstance(value, Path):
                return str(value)

            else:
                return value

        for key, value in vars(cls).items():
            if key == '_guilds':  # custom handling for guilds
                for idx, guild in cls._guilds.items():
                    result.update({f'{idx}/{key}': convert_value(value) for key, value in vars(guild).items()})

            elif key.startswith('_') or callable(value) or isinstance(value, classmethod):
                continue

            else:
                result[key] = convert_value(value)

        return result


# Old Methods and Layout
class Config:
    config_version = NovaConfig.config_version
    path = NovaConfig.path
    db_path = NovaConfig.db_path

    @classmethod
    def on_init(cls):
        cls._raw = NovaConfig._raw

        # Global
        cls.bot_token = NovaConfig.bot_token
        cls.authorized_guilds = NovaConfig.authorized_guilds

        # Wiki
        cls.wiki_key = NovaConfig.wiki.key
        cls.wiki_page = NovaConfig.wiki.page
        cls.wiki_user = NovaConfig.wiki.user
        cls.wiki_endpoint = NovaConfig.wiki.endpoint

        # Guilds
        cls.attu_guild = NovaConfig.primary_guild

        # Timestamps optional (still present for bootstrapping bot if needed for now)
        Config.timestamps = Config._raw.get('timestamps', [])

    @classmethod
    def on_load(cls):
        guild = NovaConfig.guild(cls.attu_guild)

        # Users
        cls.users = guild.users

        # Channels
        cls.activity_channel = guild.channels.activity
        cls.year_vc = guild.channels.year_vc
        cls.announce_channel = guild.channels.announcements
        cls.year_link_thread = guild.channels.year_links
        cls.meta_chat_channel = guild.channels.meta_chat
        cls.lore_channels = guild.channels.lore_channels

        # Roles
        cls.announce_role = guild.roles.announcements

        # Epoch
        cls.epoch_time = guild.epoch.time
        cls.epoch_year = guild.epoch.year
        cls.epoch_length = guild.epoch.length
        cls.time_paused = guild.epoch.paused

        cls.rollover_time = guild.epoch.rollover_time

    @classmethod
    def _save(cls):  # NOTE: Unused
        logger.info(f'Writing new config to "{cls.path}"')

        with cls.path.open('w') as file:
            tomlkit.dump(cls._raw, file)

        NovaConfig.on_init()

    # --- Debug ---

    @classmethod
    def to_dict(cls):
        result = {}

        def convert_value(value):
            if isinstance(value, BaseModel):
                return {k: convert_value(v) for k, v in vars(value).items()}

            elif isinstance(value, list):
                return [convert_value(item) for item in value]

            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}

            else:
                return value

        for key, value in vars(cls).items():
            if key.startswith('_') or callable(value) or isinstance(value, classmethod):
                continue

            result[key] = convert_value(value)

        return result
