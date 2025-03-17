"""
AttuBot - Configuration Migrations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.config import NovaConfig
from attubot.logging import get_logger

logger = get_logger(__name__)

async def generic_bump(version):
    await NovaConfig.set('version', version)

# Version 1.8.0-pre2
async def import_migration():
    pass
