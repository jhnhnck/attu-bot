"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
import sys
from pathlib import Path

from attubot import __version__
from attubot.logging import get_logger

logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = __version__

    def __init__(self, file_name):
        self.file_name = Path(file_name).resolve()

    def load_from_file(self):
        if not Path(self.file_name).exists():
            logger.error('Config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{self.file_name}"')

        with Path(self.file_name).open() as file:
            self._raw = json.loads(file.read())

        # Unpack raw json
        if self._raw['config_version'] != self.config_version:
            logger.info('Incompatible config version!')
            sys.exit(1)


    def _save(self):
        logger.info(f'Writing new config to "{self.file_name}"')

        with Path(self.file_name).open('w') as file:
            file.write(json.dumps(self._raw, indent=4))

        self.load_from_file()

    def add_timestamp(self, timestamp):
        self._raw['timestamps'].append(timestamp)
        self._save()

    def set_epoch(self, time, year: int):
        self._raw['epoch']['time'] = int(time)
        self._raw['epoch']['year'] = year
        self._save()

    def set_epoch_length(self, length: int):
        self._raw['epoch']['length'] = length
        self._save()

    @property
    def time_paused(self):
        return self._raw['epoch']['paused']

    @time_paused.setter
    def time_paused(self, value: bool):
        self._raw['epoch']['paused'] = value
        self._save()
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
