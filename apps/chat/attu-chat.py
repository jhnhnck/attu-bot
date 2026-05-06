#!/usr/bin/env python
"""
AttuBot - Chat/RAG entrypoint
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Usage:
    python attu-chat.py ingestor  # Launch the chat/RAG ingestor
"""

import sys
import time
import traceback
from os import environ

from doom_bot import __build_time__
from doom_bot.logging import get_logger


logger = get_logger(__name__)

logger.info(f'Container Build Time: {__build_time__}')

if 'DEBUG' in environ:
    logger.debug('Debug Mode: Enabled')
else:
    logger.info('Debug Mode: Disabled')

mode = sys.argv[1] if len(sys.argv) > 1 else 'ingestor'

if mode != 'ingestor':
    logger.error(f'Unknown mode: "{mode}". Valid options: ingestor')
    sys.exit(1)

try:
    from attu_chat.ingestor import start_ingestor

    start_ingestor()

except Exception as error:
    tb_str = ''.join(traceback.format_exception(error))
    logger.error(f'{error!s}\n{tb_str}')

    if 'TEST_MODE' not in environ:
        logger.fatal('Fatal error encountered; will exit/restart in 60 secs')
        time.sleep(60)

    sys.exit(1)
