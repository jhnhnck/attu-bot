# SPDX-License-Identifier: Apache-2.0
"""nova_core.database.repositories | database repositories shim.

Re-exports the repository classes from `attu_models.repositories` so existing
`from nova_core.database.repositories import ...` sites keep working.
"""

from attu_models.repositories import *  # noqa: F403  # re-export every name from attu_models.repositories
