"""
AttuBot - Package Metadata
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

# --- Metadata ---

__title__ = 'AttuBot'
__author__ = 'jhnhnck'
__license__ = 'Apache License, Version 2.0'
__copyright__ = 'Copyright (c) 2026 John Hancock, The Attu Project'
__schema__ = '2.5.5'  # db migration version
__config_version__ = '2.5.4'  # minimum compatible config file version; bump only when TOML format changes
__email__ = 'doom@attuproject.org'
__description__ = 'A discord bot designed for automating tasks for the Attu Project'

__version__ = '78.1.4'
__build_time__ = 'Thu Aug 11 02:23:20 UTC 2022'  # stamped during docker build

# --- Re-exports for backward compatibility ---

from attubot.client import (  # noqa: F401
    _check_deps,
    _load_event_handlers,
    _load_extensions,
    _register_core_commands,
    _setup_discord_logging,
    command_ping,
    extensions_list,
    start_bot_loop,
    start_bot_loop_web,
)
from attubot.client.core import bot, config, db  # noqa: F401
