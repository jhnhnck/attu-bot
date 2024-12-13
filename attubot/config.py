"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
import sys
from os import getenv
from pathlib import Path

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = __version__
    file_name = getenv('BOT_CONFIG_FILE', './attu-bot.json')

    @staticmethod
    def init(file_name):
        logger.info('Initalizing...')
        Config.file_name = Path(file_name).resolve()
        Config._load()

    # --- Private Methods ---

    @staticmethod
    def _load():
        if not Config.file_name.exists():
            logger.error('config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{Config.file_name}"')

        with Config.file_name.open() as file:
            Config._raw = json.load(file)

        # validate config version
        if Config._raw['config_version'] != Config.config_version:
            logger.info('Incompatible config version!')
            sys.exit(1)

        # unpack raw json
        Config.bot_token = Config._raw['auth']['token']
        Config.bot_owner = Config._raw['users']['bot_owner']

        Config.wiki_key = Config._raw['wiki']['key']
        Config.wiki_page = Config._raw['wiki']['page']
        Config.wiki_user = Config._raw['wiki']['user']

        Config.activity_channel = Config._raw['channels']['activity']
        Config.year_vc = Config._raw['channels']['year_vc']
        Config.announce_channel = Config._raw['channels']['announcements']
        Config.doom_forum = Config._raw['channels']['doom_forum']
        Config.year_link_thread = Config._raw['channels']['year_links']
        Config.meta_chat_channel = Config._raw['channels']['meta_chat']
        Config.error_log_channel = Config._raw['channels']['error_log']
        Config.lore_channels = Config._raw['channels']['lore_channels']

        Config.announce_role = Config._raw['roles']['leaders']

        Config.epoch_time = Config._raw['epoch']['time']
        Config.epoch_year = Config._raw['epoch']['year']
        Config.epoch_length = Config._raw['epoch']['length']
        Config.attu_guild = Config._raw['guilds']['attu']
        Config.jhn_guild = Config._raw['guilds']['jhn']
        Config.timestamps = Config._raw['timestamps']

    @staticmethod
    def _save():
        logger.info(f'Writing new config to "{Config.file_name}"')

        with Config.file_name.open('w') as file:
            json.dump(Config._raw, file, indent=4)

        Config._load()

    # --- Public Methods ---

    @staticmethod
    def add_timestamp(timestamp):
        Config._raw['timestamps'].append(timestamp)
        Config._save()

    @staticmethod
    def set_epoch(time, year: int):
        Config._raw['epoch']['time'] = int(time)
        Config._raw['epoch']['year'] = year
        Config._save()

    @staticmethod
    def set_epoch_length(length: int):
        Config._raw['epoch']['length'] = length
        Config._save()

    @staticmethod
    def pause_time():
        Config._raw['epoch']['paused'] = True
        Config._save()

    @staticmethod
    def resume_time():
        Config._raw['epoch']['paused'] = False
        Config._save()
