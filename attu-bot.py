#!/usr/bin/env python
"""
AttuBot - Command line entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Usage:
    python attu-bot.py bot   # Launch the Discord bot (default)
    python attu-bot.py web   # Launch the web interface
"""

import sys
import time
import traceback
from os import environ

from attubot import __build_time__
from attubot.logging import get_logger

logger = get_logger(__name__)

logger.info(f'Container Build Time: {__build_time__}')

if 'DEBUG' in environ:
    logger.debug('Debug Mode: Enabled')
else:
    logger.info('Debug Mode: Disabled')

# Determine mode from CLI args (default: bot)
mode = sys.argv[1] if len(sys.argv) > 1 else 'bot'

if mode not in ('bot', 'web'):
    logger.error(f'Unknown mode: "{mode}". Valid options: bot, web')
    sys.exit(1)

try:
    if mode == 'bot':
        from attubot import start_bot_loop

        start_bot_loop()

    elif mode == 'web':
        from attubot.web.app import start_web

        start_web()

except Exception as error:
    tb_str = ''.join(traceback.format_exception(error))
    logger.error(f'{error!s}\n{tb_str}')

    if 'TEST_MODE' not in environ:
        logger.fatal('Fatal error encountered; will exit/restart in 60 secs')
        time.sleep(60)

    sys.exit(1)
