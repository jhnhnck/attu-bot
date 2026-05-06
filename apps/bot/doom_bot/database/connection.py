# SPDX-License-Identifier: Apache-2.0
"""doom_bot.database.connection | database connection shim.

Re-exports the entire connection module so callers and tests that reference
attributes like `AsyncMongoClient`, `ConfigurationError`, or `ConnectionFailure`
on `doom_bot.database.connection` keep working.
"""

from attu_models.connection import *  # noqa: F403  # re-export every name from attu_models.connection
