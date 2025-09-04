"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import datetime
import re
from os import environ, getenv
from pathlib import Path
from typing import Any, Literal, Self, TypedDict, cast, override
from zoneinfo import ZoneInfo

import tomlkit
from discord import Bot
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

    async def pack(self, value: Any) -> None:
        self.value = tomlkit.dumps({'X': value})
        await self.save()

    def unpack(self) -> Any:
        return tomlkit.loads(self.value)['X']

    @override
    def __str__(self) -> str:
        return f'{self.guild}/{self.key}={self.unpack()}'


class ParsedTokenKey(BaseModel):
    guild: int
    key: str

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
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
    def guild_validate(self) -> Self:
        if self.guild != 0 and self.guild not in NovaConfig.authorized_guilds:
            raise UnauthorizedGuild(self.guild)

        if (self.guild == 0 and self.key not in NovaConfig.global_keys) or (self.guild != 0 and self.key not in NovaConfig.guild_keys):
            raise InvalidTokenKey(self.key)

        return self

    def authorized(self, user: int, guild: int, mode: str):  # (Keeping mode level here for future usecases)
        return (self.guild == 0 and NovaConfig.is_owner(user)) or self.guild == guild

    @override
    def __str__(self) -> str:
        return f'{self.guild}/{self.key}'

# --- Components ---

class RawConfig(TypedDict):
    config_version: str
    auth: dict[str, Any]
    discord: dict[str, Any]
    imports: dict[str, Any] | None


class NovaGlobals(BaseModel):
    pass


class BotTheme(BaseModel):
    rotation: float
    max_rate: float
    bot_color: str
    guild_color: str

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        data['rotation'] = data.get('theme.rotation', 0.0)
        data['max_rate'] = data.get('theme.max_rate', 0.5)
        data['bot_color'] = data.get('theme.bot_color', '#ff0000')
        data['guild_color'] = data.get('theme.guild_color', '#ffffff')

        return data


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
    @classmethod
    def setup(cls, data: dict) -> dict:
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
    @classmethod
    def setup(cls, data: dict) -> dict:
        data['time'] = data.get('epoch.time', 0)
        data['year'] = data.get('epoch.year', 1)
        data['length'] = data.get('epoch.length', 14)
        data['paused'] = data.get('epoch.paused', True)

        th = data.get('epoch.rollover_time', '17:00').split(':')
        data['rollover_time'] = datetime.time(int(th[0]), int(th[1]), tzinfo=NovaConfig.timezone)

        return data


class GuildRoles(BaseModel):
    announcements: int

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        data['announcements'] = data.get('roles.announcements', 0)

        return data


class GuildUsers(BaseModel):
    markers: list[int]

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        data['markers'] = data.get('users.markers', [])

        return data


class GuildConfig(BaseModel):
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    id: int
    _display_name: str | None = None

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        data['channels'] = GuildChannels(**data)
        data['epoch'] = GuildEpoch(**data)
        data['roles'] = GuildRoles(**data)
        data['users'] = GuildUsers(**data)

        return data

    async def set_epoch(self, time, year: int):
        logger.warn(f'[{self.id}] Epoch changed: old={self.epoch.time},{self.epoch.year} new={int(time)},{year}')
        self.epoch.time = await NovaConfig.set('epoch.time', int(time), guild=self.id)
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

    async def reload(self) -> bool:
        return await NovaConfig.load_guild(self.id)

    @override
    def __str__(self) -> str:
        return str(self.id) if self._display_name is None else self._display_name

class GuildConfigExport(GuildConfig):
    name: str

class NovaConfigRepr(TypedDict):
    config_version: str
    path: str
    db_path: str
    timezone: str
    error_log: tuple[int, int]
    primary_guild: int
    guilds: list[GuildConfigExport]
    wiki: WikiAuth

# --- Exceptions ---

class ConfigLoadError(Exception):
    def __init__(self, reason: str):
        self.message = f'Unable to load config: {reason}'
        super().__init__(self.message)


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
    theme: BotTheme
    bot_token: str
    authorized_guilds: set[int]
    valid_guilds: list[int] = []
    error_log: tuple[int, int]
    error_hook: str
    primary_guild: int
    owner_ids: set[int]
    _bot: Bot
    _raw: RawConfig

    guild_keys: set[str]
    global_keys: set[str]
    valid_keys: set[str]

    # Dynamic Attributes
    path = Path(getenv('ATTU_CONFIG_FILE', './attu-bot.toml')).resolve()
    db_path = Path(getenv('ATTU_MARKER_DB', './markers.db')).resolve()
    timezone = ZoneInfo(getenv('TZ', 'UTC'))
    guilds: dict[int, GuildConfig] = {}
    test_mode: bool = 'TEST_MODE' in environ

    _events = {
        'init': asyncio.Event(),
        'load': asyncio.Event(),
        'ready': asyncio.Event(),
        'reload': asyncio.Event(),
    }

    # --- Event Calls ---

    @classmethod  # called first upon startup, load config file only
    def on_init(cls):
        logger.info('Starting initial config loading stage')

        if not cls.path.exists():
            logger.error('Config file missing!')
            raise ConfigLoadError('missing config file')

        logger.info(f'Loading config from "{cls.path}"')

        with cls.path.open() as file:
            cls._raw = cast(RawConfig, tomlkit.load(file))

        # validate config version
        if cls._raw['config_version'] != cls.config_version:
            logger.fatal('Incompatible config version!')
            raise ConfigLoadError('incompatible config file version')
        else:
            logger.info(f'Matched file version: {__version__}')

        # unpack into attributes
        cls.bot_token = cls._raw['auth']['bot']['token']
        cls.authorized_guilds = { *cls._raw['discord']['guilds']['authorized'] }
        cls.primary_guild = cls._raw['discord']['guilds']['primary']  # TODO: Deprecate

        try:
            cls.wiki = WikiAuth(**cls._raw['auth']['wiki'])

        except ValidationError as err:
            logger.error(f'Failed to validate wiki auth configuration: {err!s}')
            raise ConfigLoadError('invalid wiki auth configuration')

        cls._get_event('init').set()

    @classmethod  # called by markers setup after db is connected
    async def on_load(cls):
        logger.info('Starting post-connect config loading stage')

        # handle data migration
        if cls.config_version != (await cls.get('version', default=cls.config_version)):
            await cls._migrate()

        else:
            logger.info(f'Matched table version: {__version__}')

        # Populate valid keys lists
        async def unpack_keys(state: bool) -> set[str]:
            models = cast(list[NovaToken], await NovaToken.raw(f'SELECT DISTINCT key FROM novatoken WHERE {"guild=0" if state else "guild!=0"}'))  # noqa: S608
            return { token.key for token in models }

        cls.global_keys = await unpack_keys(True)
        cls.guild_keys = await unpack_keys(False)
        cls.valid_keys = { *cls.guild_keys, *cls.global_keys }

        await cls._import()  # import config overrides from file
        await cls.load_globals()  # global vars
        await cls.load_theme()

        # load guild configs
        for guild in cls.authorized_guilds:
            await cls.load_guild(guild)

        cls._get_event('load').set()

    @classmethod  # called by Bot.on_ready after connect, low priority maintenance tasks
    async def on_ready(cls, bot: Bot):
        logger.info('Starting post-ready config loading stage')
        cls._bot = bot

        for idx, guild in cls.guilds.items():
            if bot.user.id not in guild.users.markers:
                logger.info(f'Adding bot user to valid year marker authors for {idx}')

                guild.users.markers.append(bot.user.id)
                await cls.set('users.markers', guild.users.markers, guild=idx)

        cls.path.chmod(0o660)
        cls.db_path.chmod(0o660)

        # dump keys with empty values
        logger.debug('Clearing out default config keys')
        await NovaToken.filter(value='X = 0').delete()

        # manually fetch owner info ourselves bc pycord is weird
        logger.debug('Fetching bot owner info')
        bot_info = await bot.application_info()

        if bot_info.team:
            cls.owner_ids = { usr.id for usr in bot_info.team.members }
        else:
            cls.owner_ids = { bot_info.owner.id }

        if cls.test_mode:
            logger.debug('Dumping NovaConfig:', tomlkit.dumps(NovaConfig.to_dict(), sort_keys=True), sep='\n')

        # load guild names from discord and store in config object
        logger.debug('Fetching guild names')

        for idx, cfg in cls.guilds.items():
            guild = await cls._bot.fetch_guild(idx)
            cfg._display_name = guild.name or None

        cls._get_event('ready').set()

        await Tortoise.close_connections()

    # --- Public Methods ---

    @classmethod
    def parse_key(cls, key: str, guild: int = 0) -> ParsedTokenKey | None:
        try:
            return ParsedTokenKey(guild=guild, key=key)

        except Exception as err:
            logger.error(f'Caught exception in parse_key(): {err!s}')

            return None

    @classmethod
    def guild(cls, guild: int) -> GuildConfig:
        if guild in cls.authorized_guilds:
            return cls.guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    @classmethod
    def primary(cls) -> GuildConfig:
        return cls.guild(cls.primary_guild)

    @staticmethod
    async def get(key: str, guild: int = 0, default: Any = 0) -> Any:
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created and default != 0:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        elif created:
            await token.delete()
            return None

        else:
            return token.unpack()

    @staticmethod
    async def get_raw(key: str, guild: int = 0, default: Any = 0) -> NovaToken:
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created and default != 0:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        return token

    @staticmethod
    async def set(key: str, value: Any, guild: int = 0) -> Any:
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
    def is_owner(cls, user: int):
        return user in cls.owner_ids

    # --- Private Methods ---

    @classmethod
    async def _migrate(cls):
        version = await cls.get('version')

        logger.info(f'Beginning config table migration from "{version}"')
        from attubot.migrations import migration_table  # noqa: PLC0415

        for migration in migration_table:
            await migration(version)
            version = await cls.get('version')

            if cls.config_version == version:
                break

        # re-check at end of migration
        if cls.config_version != version:
            logger.fatal(f'Failed to migrate config table! Got to {await cls.get("version")}')
            raise ConfigLoadError(f'failed to migrate past {cls.get("dt_version")}')
        else:
            logger.info('Finished applying config table patches')

    @classmethod
    async def _import(cls):
        if 'imports' not in cls._raw.keys():  # noqa: SIM118
            return

        logger.info('Attempting to load imports from config file')

        for key, value in cls._raw['imports'].items():
            token_key = cls.parse_key(key)

            if token_key is not None:
                logger.info(f'Importing: {key} = {value}')
                await cls.set(token_key.key, value, guild=token_key.guild)

            else:
                logger.warn(f'Skipping import; invalid keypair: {key} = {value}')

    @classmethod
    async def load_globals(cls):
        cls.error_log = tuple(await cls.get('error_log', default=(0, 0)))
        cls.error_hook = await cls.get('error_hook', default=f'{NovaConfig.wiki.endpoint}/invalid-webhook')
        cls.primary_guild = await cls.get('primary_guild', default=NovaConfig.primary_guild)

        # trigger event if this is a reload
        if cls._get_event('load').is_set():
            cls._get_event('reload').set()

    @classmethod
    async def load_guild(cls, guild: int) -> bool:
        config = {}
        prev_state = cls.guilds.get(guild, None)

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} guild config for {guild}')
            async for token in NovaToken.filter(guild=guild):
                config[str(token.key)] = token.unpack()

            cls.guilds[guild] = GuildConfig(**config, id=guild)

            if guild not in cls.valid_guilds:
                cls.valid_guilds.append(guild)

            # trigger event if this is a reload
            if cls._get_event('load').is_set():
                cls._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'Failed to validate {guild}: {err!s}')

            if prev_state is not None:
                cls.guilds[guild] = prev_state

            return False

    @classmethod
    async def load_theme(cls) -> bool:
        config = {}
        prev_state = cls.theme if hasattr(cls, 'theme') else None

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} theme config')
            async for token in NovaToken.filter(guild=0):
                if token.key.startswith('theme.'):
                    config[str(token.key)] = token.unpack()

            cls.theme = BotTheme(**config)

            # trigger event if this is a reload
            if cls._get_event('load').is_set():
                cls._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'Failed to validate theme: {err!s}')

            if prev_state is not None:
                cls.theme = prev_state

            return False

    # --- Config Events ---

    @classmethod
    def _get_event(cls, key: str) -> asyncio.Event:
        if key in cls._events:
            return cls._events[key]
        else:
            raise ValueError(f'invalid config event: {key}')

    @classmethod
    async def wait_for_init(cls) -> Literal[True]:
        return await cls._get_event('init').wait()

    @classmethod
    async def wait_for_load(cls) -> Literal[True]:
        return await cls._get_event('load').wait()

    @classmethod
    async def wait_for_ready(cls) -> Literal[True]:
        return await cls._get_event('ready').wait()

    @classmethod
    async def wait_for_reload(cls) -> Literal[True]:
        reload = cls._get_event('reload')

        if reload.is_set():
            logger.debug('Caught new wait - reseting reload event')
            reload.clear()

        return await reload.wait()

    # --- Debug ---

    @classmethod
    def to_dict(cls, banned_keys = []) -> NovaConfigRepr:
        result = {}

        def convert_value(value):
            if isinstance(value, BaseModel):
                return {k: convert_value(v) for k, v in vars(value).items()}

            elif isinstance(value, list | set):
                return [convert_value(item) for item in value]

            elif isinstance(value, dict):
                return {k: convert_value(v) for k, v in value.items()}

            elif isinstance(value, Path | ZoneInfo):
                return str(value)

            else:
                return value

        for key, value in vars(cls).items():
            if key == 'guilds':  # custom handling for guilds
                guilds = []

                for idx, guild in cls.guilds.items():
                    guilds.append({**{ 'name': str(guild) }, **{ key: convert_value(value) for key, value in vars(guild).items() }})

                result[key] = guilds

            elif key in banned_keys or key.startswith('_') or callable(value) or isinstance(value, classmethod) or value is None:
                continue

            else:
                result[key] = convert_value(value)

        return cast(NovaConfigRepr, result)


    @classmethod
    def to_repr(cls)-> NovaConfigRepr:
        banned_keys = ['bot_token', 'global_keys', 'guild_keys', 'valid_keys', 'test_mode', 'authorized_guilds', 'valid_guilds']
        return cls.to_dict(banned_keys=banned_keys)
