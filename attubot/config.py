"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
from datetime import time
from os import getenv
from pathlib import Path
from zoneinfo import ZoneInfo

import toml

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = __version__
    file_name = None

    @staticmethod
    def init():
        Config.file_name = Path(getenv('BOT_CONFIG_FILE', './attu-bot.toml')).resolve()
        Config._load()

    # --- Private Methods ---

    @staticmethod
    def _load():
        if not Config.file_name.exists():
            logger.error('Config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{Config.file_name}"')

        with Config.file_name.open() as file:
            Config._raw = toml.load(file)

        # validate config version
        if Config._raw['config_version'] != Config.config_version:
            logger.info('Incompatible config version!')
            sys.exit(1)

        # unpack raw toml
        Config.bot_token = Config._raw['auth']['bot']['token']

        Config.wiki_key = Config._raw['auth']['wiki']['key']
        Config.wiki_page = Config._raw['auth']['wiki']['page']
        Config.wiki_user = Config._raw['auth']['wiki']['user']
        Config.wiki_endpoint = Config._raw['auth']['wiki']['endpoint']

        Config.bot_owner = Config._raw['discord']['users']['bot_owner']

        Config.activity_channel = Config._raw['discord']['channels']['activity']
        Config.year_vc = Config._raw['discord']['channels']['year_vc']
        Config.announce_channel = Config._raw['discord']['channels']['announcements']
        Config.doom_forum = Config._raw['discord']['channels']['doom_forum']
        Config.year_link_thread = Config._raw['discord']['channels']['year_links']
        Config.meta_chat_channel = Config._raw['discord']['channels']['meta_chat']
        Config.error_log_channel = Config._raw['discord']['channels']['error_log']
        Config.lore_channels = Config._raw['discord']['channels']['lore_channels']

        Config.announce_role = Config._raw['discord']['roles']['leaders']

        Config.attu_guild = Config._raw['discord']['guilds']['attu']
        Config.jhn_guild = Config._raw['discord']['guilds']['jhn']

        Config.epoch_time = Config._raw['epoch']['time']
        Config.epoch_year = Config._raw['epoch']['year']
        Config.epoch_length = Config._raw['epoch']['length']
        Config.time_paused = Config._raw['epoch']['paused']

        th = Config._raw['epoch']['rollover_time'].split(':')
        Config.rollover_time = time(int(th[0]), int(th[1]), tzinfo=ZoneInfo(getenv('TZ')))

        Config.timestamps = Config._raw['timestamps']

    @staticmethod
    def _save():
        logger.info(f'Writing new config to "{Config.file_name}"')

        with Config.file_name.open('w') as file:
            toml.dump(Config._raw, file)

        Config._load()

    # --- Public Methods ---

    @staticmethod
    def add_timestamp(timestamp):
        logger.warn(f'Timestamp appended: new={timestamp}')

        Config._raw['timestamps'].append(timestamp)
        Config._save()

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
