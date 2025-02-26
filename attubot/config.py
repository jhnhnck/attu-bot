"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
from datetime import time
from os import getenv
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import toml

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = __version__
    path = None

    @staticmethod
    def init():
        Config.path = Path(getenv('ATTU_CONFIG_FILE', './attu-bot.toml')).resolve()
        Config.db_path = Path(getenv('ATTU_MARKER_DB', './markers.db')).resolve()

        Config._load()

    def on_ready(bot):
        if bot.user.id not in Config.users.markers:
            logger.info('Adding bot user to valid year marker authors')
            Config.users.markers.append(bot.user.id)

        Config.path.chmod(0o660)
        Config.db_path.chmod(0o660)

    # --- Private Methods ---

    @staticmethod
    def _load():
        if not Config.path.exists():
            logger.error('Config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{Config.path}"')

        with Config.path.open() as file:
            Config._raw = toml.load(file)

        # validate config version
        if Config._raw['config_version'] != Config.config_version:
            logger.fatal('Incompatible config version!')
            sys.exit(1)
        else:
            logger.info(f'Matched version: {__version__}')

        # --- Unpack into Attributes ---

        Config.bot_token = Config._raw['auth']['bot']['token']

        Config.wiki_key = Config._raw['auth']['wiki']['key']
        Config.wiki_page = Config._raw['auth']['wiki']['page']
        Config.wiki_user = Config._raw['auth']['wiki']['user']
        Config.wiki_endpoint = Config._raw['auth']['wiki']['endpoint']

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
