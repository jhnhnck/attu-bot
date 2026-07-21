# SPDX-License-Identifier: Apache-2.0
"""attu_server.preflight | refuse to start when mongo schema is incompatible."""

from attu_models.connection import MongoStorage
from attu_server import __expected_schema__


class PreflightError(Exception):
    pass


async def check_schema(storage: MongoStorage) -> None:
    """fail closed if the bot has not yet migrated the db to a compatible schema.

    the bot owns migrations; the server only reads. compose's depends_on holds the
    server back until the bot reports healthy, but this is the belt-and-braces check
    in case compose ordering is bypassed (local dev, kube, etc.).
    """
    db = storage.get_db()
    doc = await db.global_config.find_one({'config_type': 'system'})
    if doc is None:
        raise PreflightError('system config missing; bot has not booted yet')

    version = doc.get('version')
    if version != __expected_schema__:
        raise PreflightError(f'schema mismatch: db={version!r} expected={__expected_schema__!r}')
