"""
AttuBot - Database Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

# Re-export from submodules for backward compatibility
from attubot.database.connection import MongoStorage
from attubot.database.models import (
    GuildConfigDocument,
    ReloadSignalDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)
from attubot.database.repositories import (
    ConfigRepository,
    ReloadSignalRepository,
    YearMarkerRepository,
    YearRepository,
)

__all__ = [
    'ConfigRepository',
    'GuildConfigDocument',
    'MongoStorage',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'SystemConfigDocument',
    'ThemeDocument',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
]
