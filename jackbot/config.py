"""
JackBot - Handles setup and bot configuration
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from os import getenv, path

import json

from jackbot.logging import get_logger
logger = get_logger(__name__)

# --- Config Class ---

class Config:
    config_version = 'v1.0'
    changed = False

    def __init__(self, file_name):
        self.file_name = path.abspath(file_name)

    def load_from_file(self):
        if not path.exists(self.file_name):
            logger.info('Config file missing; regenerating...')
            self.changed = True
            self.save_to_file()

        logger.info(f'Loading config from "{self.file_name}"')

        with open(self.file_name, 'r') as file:
            self._raw = json.loads(file.read())

        # Unpack raw json
        ### do stuff here ###

    def save_to_file(self):
        if not self.changed:
            logger.info(f'Config unchanged; skipping save')
            return

        logger.info(f'Saving config to "{self.file_name}"')

        self._raw = {
            'config_version': self.config_version
        }

        with open(self.file_name, 'w') as file:
            file.write(json.dumps(self._raw, indent=4))
