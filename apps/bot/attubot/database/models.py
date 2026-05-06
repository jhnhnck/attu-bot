"""
AttuBot - Database Documents Shim
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Re-exports the document classes from `attu_models.documents` so existing
`from attubot.database.models import ...` sites keep working. Several inline
helper types (`ChatChannelConfig`, `MessageAuthor`, `MessageContent`,
`MessageRefs`) are defined in the same source module, so re-export the whole
namespace via star import.
"""

from attu_models.documents import *  # noqa: F403  # re-export every name from attu_models.documents
