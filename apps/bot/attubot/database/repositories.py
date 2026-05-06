"""
AttuBot - Database Repositories Shim
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Re-exports the repository classes from `attu_models.repositories` so existing
`from attubot.database.repositories import ...` sites keep working.
"""

from attu_models.repositories import *  # noqa: F403  # re-export every name from attu_models.repositories
