"""
AttuBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv, path

import json
import sys

from jackbot.logging import get_logger
logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = 'v1.1'

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

        self.db_pass = self._raw['database']['password']
        self.db_user = self._raw['database']['username']
        self.db_host = self._raw['database']['hostname']

        self.rm_id = self._raw['role_menu']['id']

        self.bot_token = self._raw['bot']['token']

        self.game_times = self._raw['game_times']
