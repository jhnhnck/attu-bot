"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv, path

import json
import sys

from attubot.logging import get_logger
logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = 'v1.4'

    def __init__(self, file_name):
        self.file_name = path.abspath(file_name)

    def load_from_file(self):
        if not path.exists(self.file_name):
            logger.error('Config file missing!')
            sys.exit(1)

        logger.info(f'Loading config from "{self.file_name}"')

        with open(self.file_name, 'r') as file:
            self._raw = json.loads(file.read())

        # Unpack raw json
        if self._raw['config_version'] != self.config_version:
            logger.info('Incompatible config version!')
            sys.exit(1)

        self.bot_token = self._raw['auth']['token']

        self.wiki_key = self._raw['wiki']['key']
        self.wiki_page = self._raw['wiki']['page']
        self.wiki_user = self._raw['wiki']['user']

        self.activity_channel = self._raw['channels']['activity']
        self.year_vc = self._raw['channels']['year_vc']
        self.announce_channel = self._raw['channels']['announcements']
        self.doom_forum = self._raw['channels']['doom_forum']
        self.year_link_thread = self._raw['channels']['year_links']
        self.meta_chat_channel = self._raw['channels']['meta_chat']
        self.lore_channels = self._raw['lore_channels']

        self.announce_role = self._raw['roles']['leaders']

        self.epoch_time = self._raw['epoch']['time']
        self.epoch_year = self._raw['epoch']['year']
        self.guild = self._raw['guild']
        self.timestamps = self._raw['timestamps']



    def add_timestamp(self, timestamp):
        logger.info(f'Saving config to "{self.file_name}"')

        self._raw['timestamps'].append(timestamp)

        with open(self.file_name, 'w') as file:
            file.write(json.dumps(self._raw, indent=4))
        logger.info(f'Saving config to "{self.file_name}"')

        self.load_from_file()
