# SPDX-License-Identifier: Apache-2.0
"""attu_models | shared mongodb document models and repositories."""

from .connection import MongoStorage
from .documents import (
    GuildConfigDocument,
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    ReloadSignalDocument,
    StarredMessageDocument,
    SystemConfigDocument,
    ThemeDocument,
    YearDocument,
    YearMarkerDocument,
)
from .repositories import (
    ConfigRepository,
    MessageRepository,
    ReloadSignalRepository,
    StarboardRepository,
    YearMarkerRepository,
    YearRepository,
)


__all__ = [
    'ConfigRepository',
    'GuildConfigDocument',
    'MessageAuthor',
    'MessageContent',
    'MessageDocument',
    'MessageRefs',
    'MessageRepository',
    'MongoStorage',
    'ReloadSignalDocument',
    'ReloadSignalRepository',
    'StarboardRepository',
    'StarredMessageDocument',
    'SystemConfigDocument',
    'ThemeDocument',
    'YearDocument',
    'YearMarkerDocument',
    'YearMarkerRepository',
    'YearRepository',
]
