"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import datetime
from os import environ, getenv
from pathlib import Path
from typing import Any, Literal, TypedDict, cast, override
from zoneinfo import ZoneInfo

import tomlkit
from pydantic import BaseModel, ValidationError, model_validator

from attubot import __schema__
from attubot.jobs import JobWorker
from attubot.logging import get_logger
from attubot.repositories import ConfigRepository

logger = get_logger(__name__)

# config object double for this file to avoid import loop
_config: 'NovaConfig'

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
    rotation: float = 0.0
    max_rate: float = 0.5
    bot_color: str = '#ff0000'
    guild_color: str = '#ffffff'

    async def save(self):
        """Save theme to MongoDB"""
        await _config.config_repo.save_theme(self)


# Wiki Credentials Container
# NOTE: API Keys stored in .toml file
class WikiAuth(BaseModel):
    key: str
    page: str
    user: str
    endpoint: str


class GuildChannels(BaseModel):
    activity: int = 0
    year_vc: int = 0
    announcements: int = 0
    year_links: int = 0
    meta_chat: int = 0
    lore_channels: list[int] = []


class GuildEpoch(BaseModel):
    time: int = 0  # TODO: Can we unify all stored dates under one class?
    year: int = 1
    length: int = 14
    paused: bool = True
    rollover_minutes: int = 1020  # Minutes since midnight (17:00 = 17*60 = 1020)

    @model_validator(mode='before')
    @classmethod
    def setup(cls, data: dict) -> dict:
        # Handle legacy rollover_time string format
        if 'rollover_time' in data and isinstance(data['rollover_time'], str):
            h, m = data['rollover_time'].split(':')
            data['rollover_minutes'] = int(h) * 60 + int(m)
            del data['rollover_time']
        elif 'rollover_minutes' not in data:
            # Default rollover time: 17:00
            data['rollover_minutes'] = 1020

        return data

    def get_rollover_time(self) -> datetime.time:
        """Get rollover time as datetime.time object with timezone"""
        hours = self.rollover_minutes // 60
        minutes = self.rollover_minutes % 60
        return datetime.time(hours, minutes, tzinfo=_config.timezone)


class GuildRoles(BaseModel):
    announcements: int = 0  # notification role for year changes


class GuildUsers(BaseModel):
    markers: list[int] = []  # user IDs authorized to create year markers


class GuildConfig(BaseModel):
    id: int
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    _display_name: str | None = None

    async def save(self):
        """Save entire guild config to MongoDB"""
        await _config.config_repo.save_guild(self)

    async def set_epoch(self, time, year: int):
        # Updates epoch start time and year number, persisting to database
        logger.warn(f'[{self.id}] Epoch changed: old={self.epoch.time},{self.epoch.year} new={int(time)},{year}')
        self.epoch.time = int(time)
        self.epoch.year = year
        await _config.config_repo.update_guild_field(self.id, 'epoch.time', int(time))
        await _config.config_repo.update_guild_field(self.id, 'epoch.year', year)

    async def set_year_length(self, length: int):
        # Updates the duration of each in-game year, persisting to database
        logger.warn(f'[{self.id}] Epoch length changed: old={self.epoch.length} new={length}')
        self.epoch.length = length
        await _config.config_repo.update_guild_field(self.id, 'epoch.length', length)

    async def pause_time(self):
        # Freezes time progression, persisting to database
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=True')
        self.epoch.paused = True
        await _config.config_repo.update_guild_field(self.id, 'epoch.paused', True)

    async def resume_time(self):
        # Resumes time progression, persisting to database
        logger.warn(f'[{self.id}] Epoch pause changed: old={self.epoch.paused} new=False')
        self.epoch.paused = False
        await _config.config_repo.update_guild_field(self.id, 'epoch.paused', False)

    async def reload(self) -> bool:
        # Reloads this guild's configuration from the database
        return await _config.load_guild(self.id)

    @override
    def __str__(self) -> str:
        return str(self.id) if self._display_name is None else self._display_name

class GuildConfigExport(GuildConfig):
    name: str

# Type definition for NovaConfig serialization
class NovaConfigRepr(TypedDict):
    config_version: str
    path: str
    timezone: str
    error_log: tuple[int, int]
    primary_guild: int
    guilds: list[GuildConfigExport]
    wiki: WikiAuth

# --- Exceptions ---

# Raised when configuration loading fails
class ConfigLoadError(Exception):
    def __init__(self, reason: str):
        self.message = f'Unable to load config: {reason}'
        super().__init__(self.message)


# Raised when accessing a non-authorized guild
class UnauthorizedGuild(Exception):
    def __init__(self, guild):
        self.message = f'Guild "{guild}" not in the authorized guilds list'
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
      - on_load: ran after database connect, loads data from MongoDB
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
        self._raw: RawConfig = None

        # MongoDB repositories
        self.config_repo: ConfigRepository = None

        # Path and environment attributes
        self.path = Path(getenv('ATTU_CONFIG_FILE', './assets/attu-bot.toml')).resolve()
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

        # Initialize MongoDB and repositories
        from attubot import db
        from attubot.repositories import ConfigRepository

        await db.connect()
        self.config_repo = ConfigRepository(db.get_db())
        await self.config_repo.init_indexes()

        # Version check
        system_config = await self.config_repo.get_system()
        if system_config:
            logger.info(f'Matched schema version: {system_config.version}')
        else:
            logger.warn('No system config found - creating defaults')
            from attubot.models import SystemConfigDocument
            await self.config_repo.save_system(SystemConfigDocument(
                version=self.config_version,
                error_log=[0, 0],
                error_hook=f'{self.wiki.endpoint}/invalid-webhook',
                primary_guild=self.primary_guild,
            ))

        # Load configurations
        await self.load_globals()
        await self.load_theme()

        # Load guild configs
        for guild in self.authorized_guilds:
            await self.load_guild(guild)

        self._get_event('load').set()

    async def on_ready(self):  # called by Bot.on_ready after connect, low priority maintenance tasks
        from attubot import bot
        logger.info('Starting post-ready config loading stage')

        for idx, guild in self.guilds.items():
            if bot.user.id not in guild.users.markers:
                logger.info(f'Adding bot user to valid year marker authors for {idx}')

                guild.users.markers.append(bot.user.id)
                await self.config_repo.update_guild_field(idx, 'users.markers', guild.users.markers)

        self.path.chmod(0o660)

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
            guild_obj = await bot.fetch_guild(idx)
            cfg._display_name = guild_obj.name or None

        self._get_event('ready').set()

    # --- Public Methods ---

    def guild(self, guild: int) -> GuildConfig:
        if guild in self.authorized_guilds:
            return self.guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    def primary(self) -> GuildConfig:
        return self.guild(self.primary_guild)

    def is_owner(self, user: int):
        return user in self.owner_ids

    # --- Private Methods ---

    async def load_globals(self):
        system = await self.config_repo.get_system()
        if system:
            self.error_log = tuple(system.error_log)
            self.error_hook = system.error_hook
            self.primary_guild = system.primary_guild

        # trigger event if this is a reload
        if self._get_event('load').is_set():
            self._get_event('reload').set()

    async def load_guild(self, guild: int) -> bool:
        prev_state = self.guilds.get(guild, None)

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} guild config for {guild}')

            doc = await self.config_repo.get_guild(guild)
            if not doc:
                logger.warn(f'No config found for guild {guild}, using defaults')
                # Create default config
                default_config = GuildConfig(
                    id=guild,
                    channels=GuildChannels(),
                    epoch=GuildEpoch(),
                    roles=GuildRoles(),
                    users=GuildUsers(),
                )
                await self.config_repo.save_guild(default_config)
                self.guilds[guild] = default_config
            else:
                # Convert document to runtime GuildConfig
                self.guilds[guild] = GuildConfig(
                    id=guild,
                    channels=GuildChannels(**doc.channels),
                    epoch=GuildEpoch(**doc.epoch),
                    roles=GuildRoles(**doc.roles),
                    users=GuildUsers(**doc.users),
                )

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
        prev_state = self.theme

        try:
            logger.info(f'{"Loading" if prev_state is None else "Reloading"} theme config')

            doc = await self.config_repo.get_theme()
            if doc:
                self.theme = BotTheme(
                    rotation=doc.rotation,
                    max_rate=doc.max_rate,
                    bot_color=doc.bot_color,
                    guild_color=doc.guild_color,
                )
            else:
                # Create defaults
                self.theme = BotTheme(
                    rotation=0.0,
                    max_rate=0.5,
                    bot_color='#ff0000',
                    guild_color='#ffffff',
                )
                await self.config_repo.save_theme(self.theme)

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
