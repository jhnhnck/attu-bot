#!/usr/bin/env python
# SPDX-License-Identifier: Apache-2.0
"""doom-bot | discord bot entry point."""

# configure logging before any repo import so module-level loggers see the right
# handlers/processors. structlog caches logger config on first emit, so anything
# that imports nova_core.* before this line could end up bound to the default
# console renderer instead of ours.
from os import environ  # must precede configure so DEBUG detection works

from attu_logging import configure as _configure_logging


_configure_logging(level='DEBUG' if 'DEBUG' in environ else None)

import sys  # noqa: E402 - configure must run before any other import
import time  # noqa: E402 - configure must run before any other import

import structlog  # noqa: E402 - configure must run before any other import

from nova_core import __build_time__  # noqa: E402 - configure must run before any repo import


logger = structlog.stdlib.get_logger(__name__)

logger.info(f'Container Build Time: {__build_time__}')

if 'DEBUG' in environ:
    logger.debug('Debug Mode: Enabled')
else:
    logger.info('Debug Mode: Disabled')

mode = sys.argv[1] if len(sys.argv) > 1 else 'bot'

if mode != 'bot':
    logger.error(f'Unknown mode: "{mode}". Valid options: bot')
    sys.exit(1)

try:
    if mode == 'bot':
        from nova_core.client import start_bot_loop

        start_bot_loop()

except Exception:
    logger.exception('fatal error in bot loop')

    if 'TEST_MODE' not in environ:
        logger.critical('Fatal error encountered; will exit/restart in 60 secs')
        time.sleep(60)

    sys.exit(1)
