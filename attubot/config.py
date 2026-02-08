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
from typing import Any, Literal, TypedDict, cast, override
from zoneinfo import ZoneInfo

import tomlkit
from discord import Bot
from pydantic import BaseModel, ValidationError, model_validator
from tortoise import Tortoise, fields
from tortoise.models import Model

from attubot import __schema__
from attubot.jobs import JobWorker
from attubot.logging import get_logger

logger = get_logger(__name__)

# config object double for this file to avoid import loop
_config: 'NovaConfig'

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

    def authorized(self, user: int, guild: int, mode: str):  # (Keeping mode level here for future usecases)
        return (self.guild == 0 and _config.is_owner(user)) or self.guild == guild

    @override
    def __str__(self) -> str:
        return f'{self.guild}/{self.key}'

# --- Components ---

# Type definition for the raw TOML config file structure
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
        data['rollover_time'] = datetime.time(int(th[0]), int(th[1]), tzinfo=_config.timezone)

        return data


class GuildRoles(BaseModel):
    announcements: int  # notification role for year changes

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
        self.epoch.time = await _config.set('epoch.time', int(time), guild=self.id)
        self.epoch.year = await _config.set('epoch.year', year, guild=self.id)

    async def set_year_length(self, length: int):
        logger.warn(f'[{self.id}] Epoch length changed: old={self.epoch.length} new={length}')
        self.epoch.length = await _config.set('epoch.length', length, guild=self.id)

    async def pause_time(self):
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=True')
        self.epoch.paused = await _config.set('epoch.paused', True, guild=self.id)

    async def resume_time(self):
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=False')
        self.epoch.paused = await _config.set('epoch.paused', False, guild=self.id)

    async def reload(self) -> bool:
        # Reloads this guild's configuration from the database
        return await _config.load_guild(self.id)

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

    def __init__(self):
        # Assign to module-level singleton
        global _config  # noqa: PLW0603
        _config = self

        # Core attributes
        self.config_version: str = __schema__
        self.wiki: WikiAuth = None
        self.theme: BotTheme = None
        self.job_worker: JobWorker = None
        self.bot_token: str = None
        self.authorized_guilds: set[int] = set()
        self.valid_guilds: list[int] = []
        self.error_log: tuple[int, int] = None
        self.error_hook: str = None
        self.primary_guild: int = None
        self.owner_ids: set[int] = set()
        self._bot: Bot = None
        self._raw: RawConfig = None

        # Key tracking
        self.guild_keys: set[str] = set()
        self.global_keys: set[str] = set()
        self.valid_keys: set[str] = set()

        # Path and environment attributes
        self.path = Path(getenv('ATTU_CONFIG_FILE', './assets/attu-bot.toml')).resolve()
        self.db_path = Path(getenv('ATTU_MARKER_DB', './assets/markers.db')).resolve()
        self.timezone = ZoneInfo(getenv('TZ', 'UTC'))
        self.guilds: dict[int, GuildConfig] = {}
        self.test_mode: bool = 'TEST_MODE' in environ

        # Event system
        self._events = {
            'init': asyncio.Event(),
            'load': asyncio.Event(),
            'ready': asyncio.Event(),
            'reload': asyncio.Event(),
        }

    # --- Event Calls ---

    def on_init(self):  # called first upon startup, load config file only
        logger.info('Starting initial config loading stage')

        if not self.path.exists():
            logger.error('Config file missing!')
            raise ConfigLoadError('missing config file')

        logger.info(f'Loading config from "{self.path}"')

        with self.path.open() as file:
            self._raw = cast(RawConfig, tomlkit.load(file))

        # validate config version
        if self._raw['config_version'] != self.config_version:
            logger.fatal('Incompatible config version!')
            raise ConfigLoadError('incompatible config file version')
        else:
            logger.info(f'Matched file version: {__schema__}')

        # unpack into attributes
        self.bot_token = self._raw['auth']['bot']['token']
        self.authorized_guilds = { *self._raw['discord']['guilds']['authorized'] }
        self.primary_guild = self._raw['discord']['guilds']['primary']  # TODO: Deprecate

        try:
            self.wiki = WikiAuth(**self._raw['auth']['wiki'])

        except ValidationError as err:
            logger.error(f'Failed to validate wiki auth configuration: {err!s}')
            raise ConfigLoadError('invalid wiki auth configuration')

        # initialize job worker
        self.job_worker = JobWorker()

        self._get_event('init').set()

    async def on_load(self):  # called by markers setup after db is connected
        logger.info('Starting post-connect config loading stage')

        # handle data migration
        if self.config_version != (await self.get('version', default=self.config_version)):
            await self._migrate()

        else:
            logger.info(f'Matched table version: {__schema__}')

        # Populate valid keys lists
        async def unpack_keys(state: bool) -> set[str]:
            models = cast(list[NovaToken], await NovaToken.raw(f'SELECT DISTINCT key FROM novatoken WHERE {"guild=0" if state else "guild!=0"}'))  # noqa: S608
            return { token.key for token in models }

        self.global_keys = await unpack_keys(True)
        self.guild_keys = await unpack_keys(False)
        self.valid_keys = { *self.guild_keys, *self.global_keys }

        await self._import()  # import config overrides from file
        await self.load_globals()  # global vars
        await self.load_theme()

        # load guild configs
        for guild in self.authorized_guilds:
            await self.load_guild(guild)

        self._get_event('load').set()

    async def on_ready(self, bot: Bot):  # called by Bot.on_ready after connect, low priority maintenance tasks
        logger.info('Starting post-ready config loading stage')
        self._bot = bot

        for idx, guild in self.guilds.items():
            if bot.user.id not in guild.users.markers:
                logger.info(f'Adding bot user to valid year marker authors for {idx}')

                guild.users.markers.append(bot.user.id)
                await self.set('users.markers', guild.users.markers, guild=idx)

        self.path.chmod(0o660)
        self.db_path.chmod(0o660)

        # dump keys with empty values
        logger.debug('Clearing out default config keys')
        await NovaToken.filter(value='X = 0').delete()

        # manually fetch owner info ourselves bc pycord is weird
        logger.debug('Fetching bot owner info')
        bot_info = await bot.application_info()

        if bot_info.team:
            self.owner_ids = { usr.id for usr in bot_info.team.members }
        else:
            self.owner_ids = { bot_info.owner.id }

        if self.test_mode:
            logger.debug('Dumping NovaConfig:', tomlkit.dumps(self.to_dict(), sort_keys=True), sep='\n')

        # load guild names from discord and store in config object
        logger.debug('Fetching guild names')

        for idx, cfg in self.guilds.items():
            guild = await self._bot.fetch_guild(idx)
            cfg._display_name = guild.name or None

        self._get_event('ready').set()

        await Tortoise.close_connections()

    # --- Public Methods ---

    def parse_key(self, key: str, guild: int = 0) -> ParsedTokenKey | None:
        try:
            parsed = ParsedTokenKey(guild=guild, key=key)

            # Validate guild authorization and key existence
            if parsed.guild != 0 and parsed.guild not in self.authorized_guilds:
                raise UnauthorizedGuild(parsed.guild)

            if (parsed.guild == 0 and parsed.key not in self.global_keys) or (parsed.guild != 0 and parsed.key not in self.guild_keys):
                raise InvalidTokenKey(parsed.key)

            return parsed

        except Exception as err:
            logger.error(f'Caught exception in parse_key(): {err!s}')

            return None

    def guild(self, guild: int) -> GuildConfig:
        if guild in self.authorized_guilds:
            return self.guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    def primary(self) -> GuildConfig:
        return self.guild(self.primary_guild)

    async def get(self, key: str, guild: int = 0, default: Any = 0) -> Any:
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created and default != 0:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        elif created:
            await token.delete()
            return None

        else:
            return token.unpack()

    async def get_raw(self, key: str, guild: int = 0, default: Any = 0) -> NovaToken:
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        if created and default != 0:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}] default={default}')
            await token.pack(default)

        return token

    async def set(self, key: str, value: Any, guild: int = 0) -> Any:
        token, created = await NovaToken.get_or_create(guild=guild, key=key.lower())

        logger.debug(f'Key {"Created" if created else "Changed"} [{guild}/{key.lower()}] old={token.unpack()} new={value}')
        await token.pack(value)

        return value  # condenses update methods

    async def delete(self, key: str, guild: int = 0):
        token = await NovaToken.get_or_none(guild=guild, key=key.lower())

        if token is not None:
            logger.debug(f'Key Removed [{guild}/{key.lower()}] value={token.unpack()}')
            await token.delete()
        else:
            logger.warn(f'Key Not Set [{guild}/{key.lower()}]; Cannot Remove')

    def is_owner(self, user: int):
        return user in self.owner_ids

    # --- Private Methods ---

    async def _migrate(self):
        version = await self.get('version')

        logger.info(f'Beginning config table migration from "{version}"')
        from attubot.migrations import migration_table

        for migration in migration_table:
            await migration(version)
            version = await self.get('version')

            if self.config_version == version:
                break

        # re-check at end of migration
        if self.config_version != version:
            logger.fatal(f'Failed to migrate config table! Got to {await self.get("version")}')
            raise ConfigLoadError(f'failed to migrate past {self.get("dt_version")}')
        else:
            logger.info('Finished applying config table patches')

    async def _import(self):
        if 'imports' not in self._raw.keys():  # noqa: SIM118
            return

        logger.info('Attempting to load imports from config file')

        for key, value in self._raw['imports'].items():
            token_key = self.parse_key(key)

            if token_key is not None:
                logger.info(f'Importing: {key} = {value}')
                await self.set(token_key.key, value, guild=token_key.guild)

            else:
                logger.warn(f'Skipping import; invalid keypair: {key} = {value}')

    async def load_globals(self):
        self.error_log = tuple(await self.get('error_log', default=(0, 0)))
        self.error_hook = await self.get('error_hook', default=f'{self.wiki.endpoint}/invalid-webhook')
        self.primary_guild = await self.get('primary_guild', default=self.primary_guild)

        # trigger event if this is a reload
        if self._get_event('load').is_set():
            self._get_event('reload').set()

    async def load_guild(self, guild: int) -> bool:
        config = {}
        prev_state = self.guilds.get(guild, None)

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} guild config for {guild}')
            async for token in NovaToken.filter(guild=guild):
                config[str(token.key)] = token.unpack()

            self.guilds[guild] = GuildConfig(**config, id=guild)

            if guild not in self.valid_guilds:
                self.valid_guilds.append(guild)

            # trigger event if this is a reload
            if self._get_event('load').is_set():
                self._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'Failed to validate {guild}: {err!s}')

            if prev_state is not None:
                self.guilds[guild] = prev_state

            return False

    async def load_theme(self) -> bool:
        config = {}
        prev_state = self.theme

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} theme config')
            async for token in NovaToken.filter(guild=0):
                if token.key.startswith('theme.'):
                    config[str(token.key)] = token.unpack()

            self.theme = BotTheme(**config)

            # trigger event if this is a reload
            if self._get_event('load').is_set():
                self._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'Failed to validate theme: {err!s}')

            if prev_state is not None:
                self.theme = prev_state

            return False

    # --- Config Events ---

    def _get_event(self, key: str) -> asyncio.Event:
        if key in self._events:
            return self._events[key]
        else:
            raise ValueError(f'invalid config event: {key}')

    async def wait_for_init(self) -> Literal[True]:
        return await self._get_event('init').wait()

    async def wait_for_load(self) -> Literal[True]:
        return await self._get_event('load').wait()

    async def wait_for_ready(self) -> Literal[True]:
        return await self._get_event('ready').wait()

    async def wait_for_reload(self) -> Literal[True]:
        reload = self._get_event('reload')

        if reload.is_set():
            logger.debug('Caught new wait - reseting reload event')
            reload.clear()

        return await reload.wait()

    # --- Debug ---

    def to_dict(self, banned_keys = []) -> NovaConfigRepr:
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

        for key, value in vars(self).items():
            if key == 'guilds':  # custom handling for guilds
                guilds = []

                for idx, guild in self.guilds.items():
                    guilds.append({**{ 'name': str(guild) }, **{ key: convert_value(value) for key, value in vars(guild).items() }})

                result[key] = guilds

            elif key in banned_keys or key.startswith('_') or callable(value) or value is None:
                continue

            else:
                result[key] = convert_value(value)

        return cast(NovaConfigRepr, result)


    def to_repr(self) -> NovaConfigRepr:
        banned_keys = ['bot_token', 'global_keys', 'guild_keys', 'valid_keys', 'test_mode', 'authorized_guilds', 'valid_guilds']
        return self.to_dict(banned_keys=banned_keys)
