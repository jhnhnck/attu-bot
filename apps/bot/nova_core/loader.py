# SPDX-License-Identifier: Apache-2.0
"""nova_core.loader | feature manifest loader.

repo injection pattern (a): the loader calls `mod.init_repos(db)` on the feature module
after loading its manifest, if the function exists. `init_repos` is responsible for
instantiating the feature's repository classes with `db` and setting them as module-level
singletons; this mirrors the `_wire_repos()` pattern in `nova_core.database.__init__`
(import module, set `module._attr = repo_instance`) while letting each feature own its own
attribute names. repository_classes in the manifest are present for discovery; injection is
delegated to init_repos. index creation (repo.init_indexes()) must be called inside
init_repos since _wire_documents is synchronous.

migration ordering: load_all appends each feature's migrations in enabled-list order to
_pending_migrations; drain_migrations() returns and clears the accumulated list so the
caller can run them in a single pass after all features are loaded.
"""

import importlib
from collections import namedtuple
from collections.abc import Callable

import structlog

from nova_core.manifest import FeatureManifest


logger = structlog.stdlib.get_logger(__name__)

BasePackageSpec = namedtuple('BasePackageSpec', ['name', 'tasks', 'setup'])

# stub for phase 2; populated with ping, version, db-backup, error-hook, reload-watcher
BASE_PACKAGE: tuple[BasePackageSpec, ...] = ()


class FeatureContext:
    """Orchestrates loading and wiring of feature manifests.

    All four resources (bot, scheduler, config, db) are stored as instance attrs
    and threaded through the wire methods so features never need to import singletons.
    """

    def __init__(self, bot, scheduler, config, db):
        self.bot = bot
        self.scheduler = scheduler
        self.config = config
        self.db = db
        self._pending_migrations: list = []

    def load_base(self, specs) -> None:
        """Load base package specs in order; each spec wires tasks and setup."""
        for spec in specs:
            self._wire_tasks(spec.tasks)
            self._wire_setup(spec.setup)

    def load_all(self, enabled: list[str]) -> None:
        """Import and load all enabled feature packages by dotted module path."""
        for name in enabled:
            try:
                mod = importlib.import_module(name)
            except ImportError:
                logger.warning(f"feature '{name}' not found, skipping")
                continue

            manifest = getattr(mod, 'manifest', None)
            if manifest is None:
                logger.warning(f"feature '{name}' has no manifest, skipping")
                continue
            if not isinstance(manifest, FeatureManifest):
                logger.warning(f"feature '{name}'.manifest is not a FeatureManifest, skipping")
                continue

            self.load_feature(manifest, _mod=mod)

    def load_feature(self, manifest: FeatureManifest, _mod=None) -> None:
        """Wire all declared surfaces of a single feature manifest."""
        self._wire_tasks(manifest.tasks)
        self._wire_event_handlers(manifest.event_handlers)
        self._wire_setup(manifest.setup)
        self._wire_documents(manifest.document_classes, manifest.repository_classes, _mod)
        self._wire_migrations(manifest.migrations)

    def drain_migrations(self) -> list:
        """Return accumulated migrations in feature declaration order and clear the list."""
        result = list(self._pending_migrations)
        self._pending_migrations.clear()
        return result

    def _wire_tasks(self, tasks) -> None:
        """Register tasks with the scheduler; already-registered tasks are skipped."""
        registered = set(self.scheduler.registered_tasks())
        for task in tasks:
            if task not in registered:
                self.scheduler.register(task)

    def _wire_event_handlers(self, handlers: dict[str, Callable]) -> None:
        """Register event handlers via bot.add_listener(fn, name=event_name).

        bot.add_listener is the non-decorator equivalent of @bot.listen(); confirmed
        present in py-cord 2.x as the programmatic listener registration API.
        """
        for event_name, fn in handlers.items():
            self.bot.add_listener(fn, name=event_name)

    def _wire_setup(self, setup_fn) -> None:
        """Call the feature setup function with the bot if provided."""
        if setup_fn is not None:
            setup_fn(self.bot)

    def _wire_documents(self, document_classes, repository_classes=None, _mod=None) -> None:
        """Wire repository singletons via the feature module's init_repos(db) function.

        If _mod has an init_repos attribute, it is called with self.db. The module is
        responsible for instantiating each repository class and setting module-level
        singletons (e.g. _mod._reaction_repo = ReactionRepository(db)). document_classes
        and repository_classes are available for discovery by tooling; injection is
        delegated to init_repos to avoid a naming-convention requirement on the loader.
        """
        if _mod is not None and hasattr(_mod, 'init_repos'):
            _mod.init_repos(self.db)

    def _wire_migrations(self, migrations) -> None:
        """Append feature migrations to the accumulated list in declaration order."""
        self._pending_migrations.extend(migrations)
