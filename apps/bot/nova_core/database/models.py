# SPDX-License-Identifier: Apache-2.0
"""nova_core.database.models | database documents shim."""

from attu_models.documents import *  # noqa: F403 - re-export every name from attu_models.documents
from nova_core.starboard.documents import StarredMessageDocument  # noqa: F401 - moved from attu_models; explicit re-export for backward compat
