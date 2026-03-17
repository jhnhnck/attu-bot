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

import anyio
import tomlkit
from pydantic import BaseModel, PrivateAttr, ValidationError, model_validator

from attubot import __schema__
from attubot.database.models import ChatConfigDocument
from attubot.database.repositories import ChatConfigRepository, ConfigRepository
from attubot.logging import get_logger


logger = get_logger(__name__)

# config object double for this file to avoid import loop
_config: 'NovaConfig'

# --- Components ---


# Type definition for the raw TOML config file structure
class RawConfig(TypedDict):
    config_version: str
    paths: dict[str, Any]
    database: dict[str, Any]
    auth: dict[str, Any]
    discord: dict[str, Any]


class NovaGlobals(BaseModel):
    pass


class PathsConfig(BaseModel):
    assets: str = './assets'


class BackupConfig(BaseModel):
    path: str = ''
    day: str = 'sunday'
    time: str = '03:00'


class DatabaseConfig(BaseModel):
    url: str = 'mongodb://localhost:27017'
    name: str = 'doombot'


class WebConfig(BaseModel):
    secret_key: str


class WebAuthnConfig(BaseModel):
    rp_id: str = 'localhost'
    rp_name: str = 'AttuBot Configurator'
    origin: str = 'http://localhost:5000'


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
    general: int = 0
    logs: int = 0
    lore_channels: list[int] = []
    canon_channels: list[int] = []  # additional channels included in year search/link lookups


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
    bot_color: int = 0  # role whose color tracks the bot theme color


class GuildUsers(BaseModel):
    markers: list[int] = []  # user IDs authorized to create year markers


class ChatConfig(BaseModel):
    qdrant_url: str = 'http://qdrant:6333'
    ingestor_api_url: str = 'http://ingestor:8001'
    ingestor_token: str = ''
    llm_primary_url: str = 'http://localhost:8080'
    llm_fallback_url: str = 'http://llama-server:8080'
    llm_api_key: str = ''
    anthropic_api_key: str = ''
    ask_cooldown_seconds: int = 30
    embedding_model: str = 'all-MiniLM-L6-v2'
    prompts_dir: str = 'assets/prompts'


class GuildStarboard(BaseModel):
    channel_id: int = 0  # channel where starboard posts are sent
    emojis: dict[str, str] = {}  # emoji_str -> hex color (e.g. '⭐' -> '#EEDD20')
    valid_bots: list[int] = []  # bot IDs allowed to contribute legacy stars


class GuildConfig(BaseModel):
    id: int
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    starboard: GuildStarboard = GuildStarboard()
    _display_name: str | None = PrivateAttr(default=None)

    async def save(self):
        """Save entire guild config to MongoDB"""
        await _config.config_repo.save_guild(self)

    async def set_epoch(self, time, year: int):
        # Updates epoch start time and year number, persisting to database
        logger.warn(f'[{self.id}] epoch changed: old={self.epoch.time},{self.epoch.year} new={int(time)},{year}')
        self.epoch.time = int(time)
        self.epoch.year = year
        await _config.config_repo.update_guild_field(self.id, 'epoch.time', int(time))
        await _config.config_repo.update_guild_field(self.id, 'epoch.year', year)

    async def set_year_length(self, length: int):
        # Updates the duration of each in-game year, persisting to database
        logger.warn(f'[{self.id}] epoch length changed: old={self.epoch.length} new={length}')
        self.epoch.length = length
        await _config.config_repo.update_guild_field(self.id, 'epoch.length', length)

    async def pause_time(self):
        # Freezes time progression, persisting to database
        logger.warn(f'[{self.id}] epoch pause changed: old={self.epoch.paused} new=True')
        self.epoch.paused = True
        await _config.config_repo.update_guild_field(self.id, 'epoch.paused', True)

    async def resume_time(self):
        # Resumes time progression, persisting to database
        logger.warn(f'[{self.id}] epoch pause changed: old={self.epoch.paused} new=False')
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
        global _config  # noqa: PLW0603 - lazy singleton initialization requires global
        _config = self

        # Core attributes
        self.config_version: str = __schema__
        self.backup: BackupConfig = None
        self.wiki: WikiAuth = None
        self.theme: BotTheme = None
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
        self.chat_config_repo: ChatConfigRepository = None

        # Config sections loaded from TOML
        self.paths: PathsConfig = None
        self.database: DatabaseConfig = None
        self.web: WebConfig = None
        self.webauthn: WebAuthnConfig = None
        self.chat: ChatConfig = None

        # Runtime config loaded from MongoDB
        self.chat_runtime: ChatConfigDocument = None

        # Path and environment attributes
        self.path = Path(getenv('ATTU_CONFIG_FILE', './assets/attu-bot.toml')).resolve()
        self.timezone = ZoneInfo(getenv('TZ', 'UTC'))
        self.guilds: dict[int, GuildConfig] = {}
        self.test_mode: bool = 'TEST_MODE' in environ
        self.web_mode: bool = False  # set by web app to skip migrations
        self.ingestor_mode: bool = False  # set by ingestor to skip discord-specific migrations

        # Event system
        self._events = {
            'init': asyncio.Event(),
            'load': asyncio.Event(),
            'ready': asyncio.Event(),
            'reload': asyncio.Event(),
        }

    # --- Event Calls ---

    def on_init(self):  # called first upon startup, load config file only
        logger.info('starting initial config loading stage')

        if not self.path.exists():
            logger.error('config file missing')
            raise ConfigLoadError('missing config file')

        logger.info(f'loading config from "{self.path}"')

        with self.path.open() as file:
            self._raw = cast(RawConfig, tomlkit.load(file))

        # validate config version
        if self._raw['config_version'] != self.config_version:
            logger.fatal('incompatible config version')
            raise ConfigLoadError('incompatible config file version')
        else:
            logger.info(f'matched file version: {__schema__}')

        # unpack into attributes
        self.bot_token = self._raw['auth']['bot']['token']
        self.authorized_guilds = {*self._raw['discord']['guilds']['authorized']}

        try:
            self.paths = PathsConfig(**self._raw.get('paths', {}))
        except ValidationError as err:
            logger.error(f'failed to validate paths configuration: {err!s}')
            raise ConfigLoadError('invalid paths configuration')

        try:
            self.database = DatabaseConfig(**self._raw.get('database', {}))
        except ValidationError as err:
            logger.error(f'failed to validate database configuration: {err!s}')
            raise ConfigLoadError('invalid database configuration')

        try:
            self.web = WebConfig(**self._raw['auth']['web'])
        except (KeyError, ValidationError) as err:
            logger.error(f'failed to validate web auth configuration: {err!s}')
            raise ConfigLoadError('invalid web auth configuration (missing [auth.web] section?)')

        try:
            self.webauthn = WebAuthnConfig(**self._raw['auth'].get('webauthn', {}))
        except ValidationError as err:
            logger.error(f'failed to validate webauthn configuration: {err!s}')
            raise ConfigLoadError('invalid webauthn configuration')

        try:
            self.wiki = WikiAuth(**self._raw['auth']['wiki'])

        except ValidationError as err:
            logger.error(f'failed to validate wiki auth configuration: {err!s}')
            raise ConfigLoadError('invalid wiki auth configuration')

        try:
            self.backup = BackupConfig(**self._raw.get('backup', {}))
        except ValidationError as err:
            logger.error(f'failed to validate backup configuration: {err!s}')
            raise ConfigLoadError('invalid backup configuration')

        try:
            self.chat = ChatConfig(**self._raw.get('chat', {}))
        except ValidationError as err:
            logger.error(f'failed to validate chat configuration: {err!s}')
            raise ConfigLoadError('invalid chat configuration')

        self._get_event('init').set()

    async def on_load(self):  # called after init_database() connects and sets up config_repo
        logger.info('starting post-connect config loading stage')

        # Version check and load system config
        system_config = await self.config_repo.get_system()
        if system_config:
            logger.info(f'current schema version: {system_config.version}')
        else:
            logger.warn('no system config found - creating defaults')
            from attubot.database.models import SystemConfigDocument

            system_config = SystemConfigDocument(
                version='0.0.0',
                error_log=[0, 0],
                error_hook=f'{self.wiki.endpoint}/invalid-webhook',
                primary_guild=next(iter(self.authorized_guilds)),
            )
            await self.config_repo.save_system(system_config)

        # Extract system config values (eliminates redundant query)
        self.error_log = tuple(system_config.error_log)
        self.error_hook = system_config.error_hook
        self.primary_guild = system_config.primary_guild

        # Load other configurations
        await self.load_theme()
        await self.load_chat_runtime()

        # Load guild configs in parallel
        async def _load_guild_safe(guild_id: int) -> tuple[int, bool]:
            """Wrapper that catches exceptions for parallel loading"""
            try:
                success = await self.load_guild(guild_id)
                return (guild_id, success)
            except Exception as e:
                logger.error(f'failed to load guild {guild_id} during parallel load: {e!s}')
                return (guild_id, False)

        results = await asyncio.gather(
            *[_load_guild_safe(guild) for guild in self.authorized_guilds],
            return_exceptions=False,
        )

        # Log any failures
        for guild_id, success in results:
            if not success:
                logger.warn(f'guild {guild_id} failed to load properly')

        # Run migrations after guild configs are loaded (migrations may need guild data)
        if system_config.version != self.config_version:
            logger.info(f'schema version mismatch: {system_config.version} -> {self.config_version}')

            if self.test_mode or self.web_mode or self.ingestor_mode:
                logger.info('skipping migrations (TEST_MODE, web_mode, or ingestor_mode)')
            else:
                logger.info('running migrations')

                from attubot.client.migrations import MigrationError, load_migration_table

                try:
                    for migration in load_migration_table:
                        await migration(system_config.version)
                        system_config = await self.config_repo.get_system()
                except MigrationError as e:
                    logger.fatal(f'migration failed - refusing to continue initialization: {e}')
                    raise

                # Reload system config after load-stage migrations
                system_config = await self.config_repo.get_system()
                logger.info(f'load-stage migrations complete: now at version {system_config.version}')

        self._get_event('load').set()

    async def on_ready(self):  # called by Bot.on_ready after connect, low priority maintenance tasks
        from attubot.client.core import bot

        logger.info('starting post-ready config loading stage')

        async def _update_guild_markers(guild_id: int, guild: GuildConfig) -> int | None:
            """Add bot user to guild markers if needed"""
            if bot.user.id not in guild.users.markers:
                logger.info(f'adding bot user to valid year marker authors for {guild_id}')
                guild.users.markers.append(bot.user.id)

                try:
                    await self.config_repo.update_guild_field(guild_id, 'users.markers', guild.users.markers)
                    return guild_id
                except Exception as e:
                    logger.error(f'failed to update markers for guild {guild_id}: {e!s}')
                    return None
            return None

        # Execute parallel updates (skip in test mode to avoid DB writes)
        if not self.test_mode:
            await asyncio.gather(
                *[_update_guild_markers(idx, guild) for idx, guild in self.guilds.items()],
                return_exceptions=False,
            )

        # Only chmod if not in test mode (volume may be read-only in tests)
        if not self.test_mode:
            await anyio.Path(self.path).chmod(0o660)

        # manually fetch owner info ourselves bc pycord is weird
        logger.debug('fetching bot owner info')
        bot_info = await bot.application_info()

        if bot_info.team:
            self.owner_ids = {usr.id for usr in bot_info.team.members}
        else:
            self.owner_ids = {bot_info.owner.id}

        if self.test_mode:
            # logger.debug('Dumping NovaConfig:', tomlkit.dumps(self.to_dict(banned_keys=['config_repo', 'job_worker']), sort_keys=True), sep='\n')
            pass

        # load guild names from discord and store in config object
        logger.debug('fetching guild names')

        async def _fetch_guild_name(guild_id: int) -> tuple[int, str | None]:
            """Fetch guild name from bot cache, falling back to API if not cached"""
            guild_obj = bot.get_guild(guild_id)
            if guild_obj is None:
                try:
                    logger.info(f'fetching guild {guild_id} info from api (not in cache)')
                    guild_obj = await bot.fetch_guild(guild_id)
                except Exception as e:
                    logger.error(f'failed to fetch guild {guild_id} from api: {e}')
                    return (guild_id, None)
            return (guild_id, guild_obj.name if guild_obj else None)

        results = await asyncio.gather(*[_fetch_guild_name(idx) for idx in self.guilds])

        # Apply results
        for guild_id, name in results:
            if guild_id in self.guilds:
                self.guilds[guild_id]._display_name = name

        # Run ready-stage migrations now that bot cache is populated
        if not self.test_mode and not self.web_mode:
            system_config = await self.config_repo.get_system()
            if system_config.version != self.config_version:
                logger.info(f'running ready-stage migrations: {system_config.version} -> {self.config_version}')

                from attubot.client.migrations import MigrationError, ready_migration_table

                try:
                    for migration in ready_migration_table:
                        await migration(system_config.version)
                        system_config = await self.config_repo.get_system()
                except MigrationError as e:
                    logger.fatal(f'ready-stage migration failed: {e}')
                    raise

                system_config = await self.config_repo.get_system()
                logger.info(f'ready-stage migrations complete: now at version {system_config.version}')

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
        """Reload system config from database (for runtime updates only)

        Note: During startup, system config is loaded directly in on_load() to avoid
        redundant database queries. This method is only used for runtime reloads.
        """
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
            logger.info(f'{"loading" if prev_state is None else "reloading"} guild config for {guild}')

            doc = await self.config_repo.get_guild(guild)
            if not doc:
                logger.warn(f'no config found for guild {guild}, using defaults')
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
                    starboard=GuildStarboard(**doc.starboard),
                )

            if guild not in self.valid_guilds:
                self.valid_guilds.append(guild)

            # trigger event if this is a reload
            if self._get_event('load').is_set():
                self._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'failed to validate {guild}: {err!s}')

            if prev_state is not None:
                self.guilds[guild] = prev_state

            return False

    async def load_theme(self) -> bool:
        prev_state = self.theme

        try:
            logger.info(f'{"loading" if prev_state is None else "reloading"} theme config')

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
            logger.error(f'failed to validate theme: {err!s}')

            if prev_state is not None:
                self.theme = prev_state

            return False

    async def load_chat_runtime(self) -> bool:
        prev_state = self.chat_runtime

        try:
            logger.info(f'{"loading" if prev_state is None else "reloading"} chat runtime config')

            doc = await self.chat_config_repo.get()
            if doc:
                self.chat_runtime = doc
            else:
                # create defaults on first run
                self.chat_runtime = ChatConfigDocument()
                await self.chat_config_repo.save(self.chat_runtime)

            # trigger event if this is a reload
            if self._get_event('load').is_set():
                self._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'failed to validate chat runtime config: {err!s}')

            if prev_state is not None:
                self.chat_runtime = prev_state

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
            logger.debug('caught new wait - reseting reload event')
            reload.clear()

        return await reload.wait()

    # --- Debug ---

    def to_dict(self, banned_keys=[]) -> NovaConfigRepr:
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
                    guilds.append({**{'name': str(guild)}, **{key: convert_value(value) for key, value in vars(guild).items()}})

                result[key] = guilds

            elif key in banned_keys or key.startswith('_') or callable(value) or value is None:
                continue

            else:
                result[key] = convert_value(value)

        return cast(NovaConfigRepr, result)

    def to_repr(self) -> NovaConfigRepr:
        banned_keys = ['bot_token', 'global_keys', 'guild_keys', 'valid_keys', 'test_mode', 'authorized_guilds', 'valid_guilds']
        return self.to_dict(banned_keys=banned_keys)
