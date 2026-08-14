# SPDX-License-Identifier: Apache-2.0
"""nova_core.reminders | reminders feature manifest."""

import asyncio

import structlog

from nova_core.manifest import FeatureManifest
from nova_core.reminders.documents import ReminderDocument
from nova_core.reminders.repositories import ReminderRepository


logger = structlog.stdlib.get_logger(__name__)

# background tasks (index init) held here to prevent garbage collection before completion
_bg_tasks: set = set()


def init_repos(db) -> None:
    """wire reminder repository singleton; called by FeatureContext._wire_documents() with MongoStorage."""
    import nova_core.reminders.task as _task_mod

    database = db.get_db()
    repo = ReminderRepository(database)
    _task_mod._reminder_repo = repo
    _task = asyncio.ensure_future(repo.init_indexes())
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)


def _setup_commands(bot) -> None:
    """register reminder slash commands; deferred import to avoid circular dependency."""
    from nova_core.commands.remind import setup as _setup

    _setup(bot)


from nova_core.reminders.task import reminder_task  # noqa: E402 - after module state


manifest = FeatureManifest(
    name='reminders',
    tasks=[reminder_task],
    setup=_setup_commands,
    document_classes=[ReminderDocument],
    repository_classes=[ReminderRepository],
)
