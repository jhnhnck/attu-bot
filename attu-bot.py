#!/usr/bin/env python3
"""
AttuBot - Command line entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import sys
import time
import traceback
from os import environ, getenv

from dotenv import load_dotenv

from attubot import core
from attubot.logging import get_logger

logger = get_logger(__name__)

load_dotenv()  # take environment variables from .env

logger.info(f'Container Build Time: {getenv("BUILD_TIME")}')

if 'DEBUG' in environ:
    logger.debug('Debug Mode: Enabled')
else:
    logger.info('Debug Mode: Disabled')

try:
    core.start_bot_loop()

except Exception as error:
    tb_str = ''.join(traceback.format_exception(error))
    logger.error(f'{error!s}\n{tb_str}')

    logger.fatal('Fatal error encountered; will exit/restart in 60 secs')
    time.sleep(60)
    sys.exit(1)
