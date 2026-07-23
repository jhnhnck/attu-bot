#!/usr/bin/env python
"""
AttuBot - Command line entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Usage:
    python doom-bot.py bot       # Launch the Discord bot (default)
"""

# configure logging before any repo import so module-level loggers see the right
# handlers/processors. structlog caches logger config on first emit, so anything
# that imports nova_core.* before this line could end up bound to the default
# console renderer instead of ours.
from attu_logging import configure as _configure_logging


_configure_logging()

import sys  # noqa: E402 - configure must run before any other import
import time  # noqa: E402 - configure must run before any other import
import traceback  # noqa: E402 - configure must run before any other import
from os import environ  # noqa: E402 - configure must run before any other import

from nova_core import __build_time__  # noqa: E402 - configure must run before any repo import
from nova_core.logging import get_logger  # noqa: E402 - configure must run before any repo import


logger = get_logger(__name__)

logger.info(f'Container Build Time: {__build_time__}')

if 'DEBUG' in environ:
    logger.debug('Debug Mode: Enabled')
else:
    logger.info('Debug Mode: Disabled')

# Determine mode from CLI args (default: bot)
mode = sys.argv[1] if len(sys.argv) > 1 else 'bot'

if mode != 'bot':
    logger.error(f'Unknown mode: "{mode}". Valid options: bot')
    sys.exit(1)

try:
    if mode == 'bot':
        from nova_core.client import start_bot_loop

        start_bot_loop()

except Exception as error:
    tb_str = ''.join(traceback.format_exception(error))
    logger.error(f'{error!s}\n{tb_str}')

    if 'TEST_MODE' not in environ:
        logger.fatal('Fatal error encountered; will exit/restart in 60 secs')
        time.sleep(60)

    sys.exit(1)
