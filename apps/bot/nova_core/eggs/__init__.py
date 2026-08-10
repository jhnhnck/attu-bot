# SPDX-License-Identifier: Apache-2.0
"""nova_core.eggs | egg collection game feature manifest."""

import asyncio

import structlog

from nova_core.eggs.documents import EggDocument, EggUserDocument
from nova_core.eggs.repositories import EggRepository, EggUserRepository
from nova_core.manifest import FeatureManifest
from nova_core.tasks.egg_cleanup import egg_cleanup_task
from nova_core.tasks.presence import presence_update_task


logger = structlog.stdlib.get_logger(__name__)

# background tasks (index init) held here to prevent garbage collection before completion
_bg_tasks: set = set()

# module-level repo singletons; wired by init_repos()
_egg_repo: EggRepository | None = None
_egg_user_repo: EggUserRepository | None = None


async def _init_indexes(egg_repo: EggRepository, egg_user_repo: EggUserRepository) -> None:
    """init egg repo indexes; errors are logged, not raised - mirrors _try_init_indexes pattern."""
    for repo, label in ((egg_repo, 'egg'), (egg_user_repo, 'egg_user')):
        try:
            await asyncio.wait_for(repo.init_indexes(), timeout=90.0)
            logger.debug(f'{label} indexes ready')
        except TimeoutError:
            logger.warning(f'{label} index init timed out after 90s (indexes may still be building in db)')
        except Exception as e:
            logger.warning(f'{label} index init failed (indexes may still be building): {e!s}')


def init_repos(db) -> None:
    """wire egg repository singletons; called by FeatureContext._wire_documents() with MongoStorage.

    db.get_db() is called here rather than passing db directly because the loader
    passes MongoStorage (the connection manager), not the AsyncDatabase handle.
    """
    import nova_core.eggs as _self
    import nova_core.eggs.hatching as _hatching

    database = db.get_db()
    _self._egg_repo = EggRepository(database)
    _self._egg_user_repo = EggUserRepository(database)
    # mirror into hatching module where all active call sites reference them
    _hatching._egg_repo = _self._egg_repo
    _hatching._egg_user_repo = _self._egg_user_repo
    # schedule async index init without blocking the synchronous call site;
    # store reference in _bg_tasks to prevent the task from being gc'd before it finishes
    _task = asyncio.ensure_future(_init_indexes(_self._egg_repo, _self._egg_user_repo))
    _bg_tasks.add(_task)
    _task.add_done_callback(_bg_tasks.discard)


def _setup_commands(bot) -> None:
    """register egg slash commands; deferred import to avoid circular dependency with nova_core.eggs."""
    from nova_core.commands.eggs import setup as _setup

    _setup(bot)


manifest = FeatureManifest(
    name='eggs',
    tasks=[egg_cleanup_task, presence_update_task],
    setup=_setup_commands,
    document_classes=[EggDocument, EggUserDocument],
    repository_classes=[EggRepository, EggUserRepository],
)
