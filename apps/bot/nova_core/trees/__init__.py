# SPDX-License-Identifier: Apache-2.0
"""nova_core.trees | family tree feature manifest."""

import asyncio

import structlog

from nova_core.manifest import FeatureManifest
from nova_core.trees.documents import FamilyDocument
from nova_core.trees.repositories import FamilyRepository


logger = structlog.stdlib.get_logger(__name__)

# background tasks (index init) held here to prevent garbage collection before completion
_bg_tasks: set = set()


def init_repos(db) -> None:
    """wire family repository singleton; called by FeatureContext._wire_documents() with MongoStorage."""
    import nova_core.trees.families as _families_mod

    database = db.get_db()
    repo = FamilyRepository(database)
    _families_mod._family_repo = repo
    _task = asyncio.ensure_future(repo.init_indexes())
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)


manifest = FeatureManifest(
    name='trees',
    document_classes=[FamilyDocument],
    repository_classes=[FamilyRepository],
)
