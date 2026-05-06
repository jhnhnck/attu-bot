# SPDX-License-Identifier: Apache-2.0
"""doom_bot.database.models | database documents shim.

Re-exports the document classes from `attu_models.documents` so existing
`from doom_bot.database.models import ...` sites keep working. Several inline
helper types (`ChatChannelConfig`, `MessageAuthor`, `MessageContent`,
`MessageRefs`) are defined in the same source module, so re-export the whole
namespace via star import.
"""

from attu_models.documents import *  # noqa: F403  # re-export every name from attu_models.documents
