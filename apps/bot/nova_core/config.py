# SPDX-License-Identifier: Apache-2.0
"""nova_core.config | handles setup and bot configuration."""

import asyncio
import datetime
from os import environ, getenv
from pathlib import Path
from typing import Any, Literal, NotRequired, TypedDict, cast, override
from zoneinfo import ZoneInfo

import anyio
import structlog
import tomlkit
from pydantic import BaseModel, Field, PrivateAttr, ValidationError, model_validator

from nova_core import __config_version__, __schema__
from nova_core.database.repositories import ConfigRepository


logger = structlog.stdlib.get_logger(__name__)


def _version_gte(version: str, minimum: str) -> bool:
    """return True if version >= minimum using simple semver tuple comparison"""
    return tuple(int(x) for x in version.split('.')) >= tuple(int(x) for x in minimum.split('.'))


# config object double for this file to avoid import loop
_config: 'NovaConfig'

# --- Components ---


class RawConfig(TypedDict):
    config_version: str
    paths: dict[str, Any]
    database: dict[str, Any]
    auth: dict[str, Any]
    discord: dict[str, Any]
    trees: dict[str, Any]
    features: NotRequired[dict[str, Any]]


class PathsConfig(BaseModel):
    assets: str = 'apps/bot/assets'


class BackupConfig(BaseModel):
    path: str = ''
    time: str = '03:00'


class DatabaseConfig(BaseModel):
    url: str = 'mongodb://localhost:27017'
    name: str = 'doombot'


class BotTheme(BaseModel):
    rotation: float = 0.0
    max_rate: float = 0.5
    bot_color: str = '#ff0000'
    guild_color: str = '#ffffff'
    logo_rings: str = '#000000'
    logo_planet: str = '#000000'
    saturation: float = 1.0
    lightness: float = 0.5
    egg_emojis: dict[str, int] = {}
    progress_emojis: dict[str, int] = {}
    ui_emojis: dict[str, int] = {}

    async def save(self):
        await _config.config_repo.save_theme(self)


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
    eggs: int = 0
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
        if 'rollover_time' in data and isinstance(data['rollover_time'], str):
            h, m = data['rollover_time'].split(':')
            data['rollover_minutes'] = int(h) * 60 + int(m)
            del data['rollover_time']
        elif 'rollover_minutes' not in data:
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
    trees_admin_role: int = 0  # role ID → "admin" in the trees service
    trees_user_role: int = 0  # role ID → "user" in the trees service


class GuildUsers(BaseModel):
    markers: list[int] = []  # user IDs authorized to create year markers


class HatchTuning(BaseModel):
    collect_cooldown_seconds: int
    hatch_cooldown_seconds: int
    animation_wait_min: int
    animation_wait_max: int
    cleanup_interval_hours: int
    cleanup_cutoff_hours: int


class HatchConfig(BaseModel):
    tuning: HatchTuning
    rarities: list[str]
    drop_weights: list[int]
    hatch_durations: dict[str, int]
    pools: dict[str, list[str]]  # key: rarity name, value: creature list


class TreesConfig(BaseModel):
    hmac_secret: str
    dev_base_url: str
    prod_base_url: str


class BridgeConfig(BaseModel):
    secret: str = Field(min_length=1)
    bot_port: int = 5050
    replay_window: int = 60


class BotConfig(BaseModel):
    name: str
    welcome_message: str


class GuildEntry(BaseModel):
    id: int
    role: str


class GuildStarboard(BaseModel):
    enabled: bool = True  # set False to silence the legacy starboard for a guild without removing code
    channel_id: int = 0  # channel where starboard posts are sent
    emojis: dict[str, str] = {}  # emoji_str -> hex color (e.g. '⭐' -> '#EEDD20')
    valid_bots: list[int] = []  # bot IDs allowed to contribute legacy stars


class GuildCCBoard(BaseModel):
    """ccboard config - replacement reaction-board with signed emoji weights and attribution.

    when `enabled` is False, the legacy starboard remains active and ccboard is dormant.
    on the False → True transition, the bot reloads the ccboard extension and re-syncs
    slash commands so the new /stars and /fix ccboard commands take effect.
    """

    enabled: bool = False  # feature flag; False keeps the legacy starboard active
    channel_id: int = 0  # channel where ccboard posts are sent
    emojis: dict[str, int] = {}  # emoji_str -> signed integer point value (e.g. {'⭐': 1, '💀': -1})
    super_bonus: int = 1  # extra points for a burst/super reaction
    threshold: int = 2  # minimum positive points required to create a board post
    points_label: str = 'stars'  # display name for points in the post content string
    positive_color: str = '#EEDD20'  # embed color when net_points > 0
    negative_color: str = '#DD2020'  # embed color when net_points <= 0
    weights_updated_at: int = 0  # unix timestamp; bumped by the web save handler when emojis or super_bonus change. drives the auditor's recount staleness predicate


class GuildConfig(BaseModel):
    id: int
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    starboard: GuildStarboard = GuildStarboard()
    ccboard: GuildCCBoard = GuildCCBoard()
    _display_name: str | None = PrivateAttr(default=None)

    async def save(self):
        await _config.config_repo.save_guild(self)

    async def set_epoch(self, time, year: int):
        logger.warning(f'[{self.id}] epoch changed: old={self.epoch.time},{self.epoch.year} new={int(time)},{year}')
        self.epoch.time = int(time)
        self.epoch.year = year
        await _config.config_repo.update_guild_field(self.id, 'epoch.time', int(time))
        await _config.config_repo.update_guild_field(self.id, 'epoch.year', year)

    async def set_year_length(self, length: int):
        logger.warning(f'[{self.id}] epoch length changed: old={self.epoch.length} new={length}')
        self.epoch.length = length
        await _config.config_repo.update_guild_field(self.id, 'epoch.length', length)

    async def pause_time(self):
        logger.warning(f'[{self.id}] epoch pause changed: old={self.epoch.paused} new=True')
        self.epoch.paused = True
        await _config.config_repo.update_guild_field(self.id, 'epoch.paused', True)

    async def resume_time(self):
        logger.warning(f'[{self.id}] epoch pause changed: old={self.epoch.paused} new=False')
        self.epoch.paused = False
        await _config.config_repo.update_guild_field(self.id, 'epoch.paused', False)

    async def reload(self) -> bool:
        return await _config.load_guild(self.id)

    @override
    def __str__(self) -> str:
        return str(self.id) if self._display_name is None else self._display_name


class GuildConfigExport(GuildConfig):
    name: str


class NovaConfigRepr(TypedDict):
    config_version: str
    path: str
    timezone: str
    error_log: tuple[int, int]
    guild_entries: list[GuildEntry]
    guilds: list[GuildConfigExport]
    bot: BotConfig
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


# --- Config Class ---


class NovaConfig:
    """three-phase init: on_init loads the config file, on_load reads from MongoDB, on_ready runs after bot connects."""

    def __init__(self):
        global _config  # noqa: PLW0603 - lazy singleton initialization requires global
        _config = self

        self.config_version: str = __schema__
        self.backup: BackupConfig = None
        self.wiki: WikiAuth = None
        self.theme: BotTheme = None
        self.bot: BotConfig = None
        self.bot_token: str = None
        self.authorized_guilds: set[int] = set()
        self.guild_entries: list[GuildEntry] = []
        self.valid_guilds: list[int] = []
        self.error_log: tuple[int, int] = None
        self.error_hook: str = None
        self.owner_ids: set[int] = set()
        self._raw: RawConfig = None

        self.config_repo: ConfigRepository = None

        self.paths: PathsConfig = None
        self.database: DatabaseConfig = None
        self.hatch: HatchConfig = None
        self.trees: TreesConfig = None
        self.bridge: BridgeConfig = None
        self.features_enabled: list[str] = []

        self.path = Path(getenv('ATTU_CONFIG_FILE', './.secrets/attu-bot.toml')).resolve()
        self.timezone = ZoneInfo(getenv('TZ', 'UTC'))
        self.guilds: dict[int, GuildConfig] = {}
        self.test_mode: bool = 'TEST_MODE' in environ
        self.web_mode: bool = False  # set by web app to skip migrations
        self.ingestor_mode: bool = False  # set by ingestor to skip discord-specific migrations

        self._events = {
            'init': asyncio.Event(),
            'load': asyncio.Event(),
            'ready': asyncio.Event(),
            'reload': asyncio.Event(),
        }

    def on_init(self):  # noqa: PLR0915, PLR0912 - sequential config section loading with try/except per section
        logger.info('starting initial config loading stage')

        if not self.path.exists():
            logger.error('config file missing')
            raise ConfigLoadError('missing config file')

        logger.info(f'loading config from "{self.path}"')

        with self.path.open() as file:
            self._raw = cast(RawConfig, tomlkit.load(file))

        if not _version_gte(self._raw['config_version'], __config_version__):
            logger.critical(f'incompatible config version: file={self._raw["config_version"]} required>={__config_version__}')
            raise ConfigLoadError(f'config file version {self._raw["config_version"]} is below required {__config_version__}')
        else:
            logger.info(f'config file version {self._raw["config_version"]} satisfies >={__config_version__}')

        self.bot_token = self._raw['auth']['bot']['token']

        discord_section = self._raw.get('discord', {})
        old_guilds = discord_section.get('guilds', {})
        if isinstance(old_guilds, dict) and ('primary' in old_guilds or 'secondary' in old_guilds):
            raise ConfigLoadError('old [discord.guilds] format detected; migrate to [[guilds]] array with role field')

        raw_entries = self._raw.get('guilds', [])
        if not raw_entries:
            raise ConfigLoadError('no [[guilds]] entries found in config file')
        try:
            self.guild_entries = [GuildEntry(**entry) for entry in raw_entries]
        except (ValidationError, TypeError) as err:
            logger.error(f'failed to validate guilds configuration: {err!s}')
            raise ConfigLoadError('invalid [[guilds]] entry (each entry requires id: int and role: str)')
        self.authorized_guilds = {entry.id for entry in self.guild_entries}

        try:
            self.bot = BotConfig(**self._raw['bot'])
        except (KeyError, ValidationError) as err:
            logger.error(f'failed to validate bot configuration: {err!s}')
            raise ConfigLoadError('invalid bot configuration (missing [bot] section?)')

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
            hatch_path = Path(self.paths.assets) / 'hatch.toml'
            if not hatch_path.exists():
                logger.error('hatch.toml missing')
                raise ConfigLoadError('missing hatch.toml')
            with hatch_path.open() as f:
                raw_hatch = cast(dict, tomlkit.load(f))
            raw_r = raw_hatch['rarities']
            self.hatch = HatchConfig(
                tuning=HatchTuning(**raw_hatch['tuning']),
                rarities=list(raw_r['names']),
                drop_weights=list(raw_r['drop_weights']),
                hatch_durations=dict(raw_r['hatch_durations']),
                pools={r: list(v['creatures']) for r, v in raw_hatch['pools'].items()},
            )
        except ConfigLoadError:
            raise
        except (ValidationError, KeyError) as err:
            logger.error(f'failed to validate hatch config: {err!s}')
            raise ConfigLoadError('invalid hatch configuration')

        try:
            self.trees = TreesConfig(**self._raw.get('trees', {}))
        except (KeyError, ValidationError) as err:
            logger.error(f'failed to validate trees configuration: {err!s}')
            raise ConfigLoadError('invalid trees configuration (missing [trees] section?)')

        bridge_raw = self._raw.get('bridge')
        if bridge_raw is not None:
            try:
                self.bridge = BridgeConfig(**bridge_raw)
            except ValidationError as err:
                logger.error(f'failed to validate bridge configuration: {err!s}')
                raise ConfigLoadError('invalid bridge configuration (check [bridge] section)')

        features_raw = self._raw.get('features', {})
        self.features_enabled = list(features_raw.get('enabled', []))

        self._get_event('init').set()

    async def on_load(self):
        logger.info('starting post-connect config loading stage')

        system_config = await self.config_repo.get_system()
        if system_config:
            logger.info(f'current schema version: {system_config.version}')
        else:
            logger.warning('no system config found; creating defaults')
            from nova_core.database.models import SystemConfigDocument

            primary_entry = self.get_guild_by_role('primary')
            system_config = SystemConfigDocument(
                version='0.0.0',
                error_log=[0, 0],
                error_hook=f'{self.wiki.endpoint}/invalid-webhook',
                primary_guild=primary_entry.id if primary_entry is not None else 0,
            )
            await self.config_repo.save_system(system_config)

        # avoids a redundant db query
        self.error_log = tuple(system_config.error_log)
        self.error_hook = system_config.error_hook

        await self.load_theme()

        async def _load_guild_safe(guild_id: int) -> tuple[int, bool]:
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

        for guild_id, success in results:
            if not success:
                logger.warning(f'guild {guild_id} failed to load properly')

        # migrations may need guild data loaded first
        if system_config.version != self.config_version:
            logger.info(f'schema version mismatch: {system_config.version} -> {self.config_version}')

            if self.test_mode or self.web_mode or self.ingestor_mode:
                logger.info('skipping migrations (TEST_MODE, web_mode, or ingestor_mode)')
            else:
                from nova_core.client.migrations import run_pending_migrations

                await run_pending_migrations(stage='load')

        self._get_event('load').set()

    async def on_ready(self):
        from nova_core.client.core import bot

        logger.info('starting post-ready config loading stage')

        async def _update_guild_markers(guild_id: int, guild: GuildConfig) -> int | None:
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

        # skip in test mode to avoid DB writes
        if not self.test_mode:
            await asyncio.gather(
                *[_update_guild_markers(idx, guild) for idx, guild in self.guilds.items()],
                return_exceptions=False,
            )

        # volume may be read-only in test/web mode
        if not self.test_mode and not self.web_mode:
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

        for guild_id, name in results:
            if guild_id in self.guilds:
                self.guilds[guild_id]._display_name = name

        # bot cache is populated by this point
        if not self.test_mode and not self.web_mode:
            system_config = await self.config_repo.get_system()
            if system_config.version != self.config_version:
                from nova_core.client.migrations import run_pending_migrations

                await run_pending_migrations(stage='ready')

        self._get_event('ready').set()

    def guild(self, guild: int) -> GuildConfig:
        if guild in self.authorized_guilds:
            return self.guilds[guild]
        else:
            raise UnauthorizedGuild(guild)

    def primary(self) -> GuildConfig:
        entry = self.get_guild_by_role('primary')
        if entry is None:
            raise UnauthorizedGuild('primary')
        return self.guild(entry.id)

    def get_guild_by_role(self, role: str) -> 'GuildEntry | None':
        """return the first guild entry matching `role`, or None if not found."""
        return next((e for e in self.guild_entries if e.role == role), None)

    def feature_config(self, name: str) -> dict:
        """return the [features.<name>] subtable as a plain dict, or {} if absent."""
        if self._raw is None:
            return {}
        features = self._raw.get('features', {})
        subtable = features.get(name, {})
        return dict(subtable)

    def is_owner(self, user: int):
        return user in self.owner_ids

    async def load_globals(self):
        """Reload system config from database (for runtime updates only)

        Note: During startup, system config is loaded directly in on_load() to avoid
        redundant database queries. This method is only used for runtime reloads.
        """
        system = await self.config_repo.get_system()
        if system:
            self.error_log = tuple(system.error_log)
            self.error_hook = system.error_hook

        if self._get_event('load').is_set():
            self._get_event('reload').set()

    async def load_guild(self, guild: int) -> bool:
        prev_state = self.guilds.get(guild, None)

        try:
            logger.info(f'{"loading" if prev_state is None else "reloading"} guild config for {guild}')

            doc = await self.config_repo.get_guild(guild)
            if not doc:
                logger.warning(f'no config found for guild {guild}, using defaults')
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
                self.guilds[guild] = GuildConfig(
                    id=guild,
                    channels=GuildChannels(**doc.channels),
                    epoch=GuildEpoch(**doc.epoch),
                    roles=GuildRoles(**doc.roles),
                    users=GuildUsers(**doc.users),
                    starboard=GuildStarboard(**doc.starboard),
                    ccboard=GuildCCBoard(**doc.ccboard),
                )

            if guild not in self.valid_guilds:
                self.valid_guilds.append(guild)

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
                    saturation=doc.saturation,
                    lightness=doc.lightness,
                    egg_emojis=doc.egg_emojis,
                    progress_emojis=doc.progress_emojis,
                    ui_emojis=doc.ui_emojis,
                )
            else:
                self.theme = BotTheme(
                    rotation=0.0,
                    max_rate=0.5,
                    bot_color='#ff0000',
                    guild_color='#ffffff',
                )
                await self.config_repo.save_theme(self.theme)

            if self._get_event('load').is_set():
                self._get_event('reload').set()

            return True

        except ValidationError as err:
            logger.error(f'failed to validate theme: {err!s}')

            if prev_state is not None:
                self.theme = prev_state

            return False

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
            logger.debug('caught new wait; reseting reload event')
            reload.clear()

        return await reload.wait()

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
            if key == 'guilds':
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
