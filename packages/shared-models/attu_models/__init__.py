"""
AttuBot - Shared MongoDB Models and Repositories
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Document and repository classes carved out from `doom_bot.database` so the future
fastapi server can read and write the same collections without depending on
pycord. The bot remains the index-creation leader; nothing in this package calls
init_indexes() at import time.
"""

from .connection import MongoStorage
from .documents import (
    BoardEntryDocument,
    ChatChannelConfig,
    ChatCharacterDocument,
    ChatConfigDocument,
    ChatSourceDocument,
    EggDocument,
    EggUserDocument,
    FamilyDocument,
    GuildConfigDocument,
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    ReactionDocument,
    ReloadSignalDocument,
    ReminderDocument,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    WikiViewDocument,
    YearDocument,
    YearMarkerDocument,
)
from .repositories import (
    ChatCharacterRepository,
    ChatConfigRepository,
    ChatSourceRepository,
    ConfigRepository,
    EggRepository,
    EggUserRepository,
    EntryRepository,
    FamilyRepository,
    MessageRepository,
    ReactionRepository,
    ReloadSignalRepository,
    ReminderRepository,
    StarboardRepository,
    WikiViewRepository,
    YearMarkerRepository,
    YearRepository,
)


__all__ = [
    'BoardEntryDocument',
    'ChatChannelConfig',
    'ChatCharacterDocument',
    'ChatCharacterRepository',
    'ChatConfigDocument',
    'ChatConfigRepository',
    'ChatSourceDocument',
    'ChatSourceRepository',
    'ConfigRepository',
    'EggDocument',
    'EggRepository',
    'EggUserDocument',
    'EggUserRepository',
    'EntryRepository',
    'FamilyDocument',
    'FamilyRepository',
    'GuildConfigDocument',
    'MessageAuthor',
    'MessageContent',
    'MessageDocument',
    'MessageRefs',
    'MessageRepository',
    'MongoStorage',
    'ReactionDocument',
    'ReactionRepository',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'ReminderDocument',
    'ReminderRepository',
    'StarboardRepository',
    'StarredMessageDocument',
    'SystemConfigDocument',
    'ThemeDocument',
    'WikiViewDocument',
    'WikiViewRepository',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
]
