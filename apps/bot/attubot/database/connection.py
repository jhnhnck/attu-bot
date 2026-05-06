"""
AttuBot - Database Connection Shim
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Re-exports the entire connection module so callers and tests that reference
attributes like `AsyncMongoClient`, `ConfigurationError`, or `ConnectionFailure`
on `attubot.database.connection` keep working.
"""

from attu_models.connection import *  # noqa: F403  # re-export every name from attu_models.connection
