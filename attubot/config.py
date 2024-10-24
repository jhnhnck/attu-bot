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

        self.bot_token = self._raw['auth']['token']
        self.bot_owner = self._raw['users']['bot_owner']

        self.wiki_key = self._raw['wiki']['key']
        self.wiki_page = self._raw['wiki']['page']
        self.wiki_user = self._raw['wiki']['user']

        self.activity_channel = self._raw['channels']['activity']
        self.year_vc = self._raw['channels']['year_vc']
        self.announce_channel = self._raw['channels']['announcements']
        self.doom_forum = self._raw['channels']['doom_forum']
        self.year_link_thread = self._raw['channels']['year_links']
        self.meta_chat_channel = self._raw['channels']['meta_chat']
        self.error_log_channel = self._raw['channels']['error_log']
        self.lore_channels = self._raw['channels']['lore_channels']

        self.announce_role = self._raw['roles']['leaders']

        self.epoch_time = self._raw['epoch']['time']
        self.epoch_year = self._raw['epoch']['year']
        self.epoch_length = self._raw['epoch']['length']
        self.attu_guild = self._raw['guilds']['attu']
        self.jhn_guild = self._raw['guilds']['jhn']
        self.timestamps = self._raw['timestamps']

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
