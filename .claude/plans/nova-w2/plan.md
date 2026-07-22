# nova-w2: feature manifest system

workstream 2 of the nova-core modularization. blocked on nova-w1; blocks workstream 3.

## goals

1. `nova_core.manifest.FeatureManifest` dataclass exists with the full contract field set (name, tasks, event_handlers, setup, guild_config_key, guild_config_model, document_classes, repository_classes, migrations); importable from any feature package without importing back into nova_core internals
   check: `python -c 'from nova_core.manifest import FeatureManifest; m = FeatureManifest(name="x"); print(m.tasks)'` exits 0 printing `[]`; `basedpyright` passes on the file

2. `nova_core.loader.FeatureContext` reads `[features].enabled` from config; dynamically imports each named feature's manifest; wires tasks, event handlers, slash commands, document/repo classes, and migrations in declaration order; missing features (ImportError or no `manifest` attribute) are silent no-ops logged at warning level; loader runs from inside `_do_ready_init()` after `init_database()`
   check: `grep -n 'FeatureContext\|load_base\|load_all' nova_core/client/events.py` shows all three after the `await init_database(...)` line

3. base package (ping, version, db-backup, error-hook, reload-watcher, bridge-health) declared as `BASE_PACKAGE` in `nova_core/loader.py`; always loaded before the manifest pass; not configurable via `[features].enabled`
   check: `nova_core.loader.BASE_PACKAGE` enumerates exactly 6 items; unit test asserts the count and names

4. repo injection mechanism designed, implemented, and documented so nova-w3 phase 0 can confirm it before coding starts
   check: `nova_core/loader.py` module docstring names the concrete pattern; decision noted in `notes/nova-core.md` feature manifest design section

## non-goals

- migrating any real feature to use a manifest (workstream 3)
- removing hardwired event dispatches from `events.py` or tasks from `tasks/__init__.py`: those removals happen feature-by-feature in w3
- casino bot scaffold (workstream 4)
- admin repl or fastapi admin endpoints (workstream 5)
- changing `GuildConfigDocument` schema in the database: document layer already stores feature config as dict blobs; no schema change needed
- nova_core rename (workstream 1 prerequisite)

## constraints

- **hard prerequisite:** nova-w1 merged to trunk; all new code assumes `nova_core.*` import paths
- loader runs in `_do_ready_init()` inside `on_ready` after `init_database()`; nova-w3 merge gate depends on this location
- python 3.13, uv workspace
- `docker compose run tests` must pass at each phase merge
- no push without explicit instruction
- import direction: feature packages import `FeatureManifest` from `nova_core.manifest`; `nova_core.manifest` and `nova_core.loader` never import from feature packages: no circular imports

## accepted risks

two residual risks from the pre-mortem. first: pycord's `bot.listen()` when called programmatically (not as a decorator) is the event-handler wiring primitive; if the calling pattern `bot.listen()(handler_fn)` misbehaves, `bot.add_listener(handler_fn, name='...')` is the fallback: phase 0 confirms which is correct before any feature depends on it. second: base package items require thin extraction wrappers at minimum; ping is an inline decorator in `client/__init__.py` today; the pre-phase-2 audit table will catch any item needing more than a thin wrapper and flag it before any phase 2 code is written.

---

## phase 0: walking skeleton

**status:** open

**scope:**

create `nova_core/manifest.py` with `FeatureManifest` as a `@dataclass`: required field `name: str`; all other fields with defaults: `tasks: list[BaseTask] = field(default_factory=list)`, `event_handlers: dict[str, Callable] = field(default_factory=dict)`, `setup: Callable[[Bot], None] | None = None`, `guild_config_key: str | None = None`, `guild_config_model: type[BaseModel] | None = None`, `document_classes: list[type] = field(default_factory=list)`, `repository_classes: list[type] = field(default_factory=list)`, `migrations: list = field(default_factory=list)`.

create `nova_core/loader.py` with `FeatureContext` class; constructor takes `bot`, `scheduler`, `config`, `db`; methods:
- `load_base(specs: Sequence[BasePackageSpec])`: iterates specs in order, calls `_wire_tasks` and `_wire_setup` on each
- `load_all(enabled: list[str])`: iterates `enabled` in order; `importlib.import_module(name)` each; catches `ImportError` and missing/wrong-type `manifest` attribute → logs warning, continues; calls `load_feature(manifest)` on each
- `load_feature(manifest: FeatureManifest)`: calls all five private wire helpers in order: `_wire_tasks`, `_wire_event_handlers`, `_wire_setup`, `_wire_documents`, `_wire_migrations`
- `_wire_tasks(tasks)`: registers each with `self.scheduler.register(task)` if not already registered
- `_wire_event_handlers(handlers)`: registers each via `self.bot.listen()(fn)` (or `self.bot.add_listener(fn, name=event)` if `listen()` is not callable in this way: confirmed in phase 0 probe); probe result documented in commit message
- `_wire_setup(setup_fn)`: calls `setup_fn(self.bot)` if not None; this is how slash command extensions are loaded (setup fns call `bot.load_extension()` internally or add commands directly)
- `_wire_documents(classes)`: no-op in phase 0 if classes is empty; stub the method so the call exists and the API is stable
- `_wire_migrations(migrations)`: no-op in phase 0 if list is empty; stub exists

also add `BasePackageSpec = namedtuple('BasePackageSpec', ['name', 'tasks', 'setup'])` to `nova_core/loader.py`; `BASE_PACKAGE: tuple[BasePackageSpec, ...] = ()` (stub for phase 2).

document the repo injection question in the module docstring: "repo injection: feature `repository_classes` are wired post-connection in `_wire_documents`; the pattern (registry vs init_repos callback) is finalized in phase 1."

create `nova_core/features/_test_feature/__init__.py` with a synthetic manifest:
- one run-once task (`run_once = True`, `run_immediately = True`) that logs `'_test_feature: startup task ran'` and sets a module-level `_task_ran = True`
- one `on_message` handler (no-op body, guild-gated, returns immediately)
- one `setup` fn that registers a `/manifest-ping` slash command on the bot
- `document_classes=[]`, `repository_classes=[]`, `migrations=[]`

wire `FeatureContext` into `nova_core/client/events.py` `_do_ready_init()`: after the `await init_database(...)` call and before `register_bot_tasks(scheduler)`, add:

```python
from nova_core.loader import FeatureContext
_loader = FeatureContext(bot=bot, scheduler=scheduler, config=config, db=db)
_loader.load_base([])  # stub; populated in phase 2
_feature_list = getattr(config, 'features_enabled', None) or []
if config.test_mode:
    _feature_list = ['nova_core.features._test_feature']
_loader.load_all(_feature_list)
```

(the `getattr` guard is removed in phase 1 when `[features]` is added to the config model.)

unit tests in `tests/python/unit/test_feature_loader.py`: mock bot, scheduler, config, db; create a mock manifest with one of each hook type; call `loader.load_feature(manifest)` and assert `_wire_tasks` called once, `_wire_event_handlers` called once, `_wire_setup` called once; assert loading a module with no `manifest` attribute logs a warning and does not raise; assert loading a non-importable name logs a warning and does not raise.

**definition of done:**
- `python -c 'from nova_core.manifest import FeatureManifest; m = FeatureManifest(name="x"); print(m.tasks)'` exits 0 printing `[]`
- `bot.listen()` programmatic pattern confirmed: unit test asserts the synthetic on_message handler fires; if `bot.listen()(fn)` fails, `bot.add_listener(fn, name='on_message')` is substituted and noted in the commit message
- `grep -n 'FeatureContext\|load_base\|load_all' nova_core/client/events.py` shows all three calls inside `_do_ready_init()` and after `await init_database(...)`
- `test_feature_loader.py` passes: task wired, event handler registered, setup fn called, unknown feature logs warning, missing manifest attr logs warning
- `docker compose run tests` passes

**cross-phase check:** `python -c 'from nova_core.manifest import FeatureManifest; from nova_core.loader import FeatureContext'` with only nova_core on PYTHONPATH; no circular imports; neither module imports from feature packages.

**merge gate:** nova-w1 merged to trunk

---

## phase 1: full manifest API, TOML feature selection, migration ordering

**status:** open

**scope:**

finalize `FeatureManifest` field set against the ccboard manifest example in `notes/nova-core.md`. review the complete field list and confirm type annotations are correct for what nova-w3 will actually declare. add `startup: Callable[[], Awaitable[None]] | None = None` field if needed: resolve this question: the contract's example manifest does not have a `startup` field, but nova-w3's wiki phase needs `_restore_wiki_views` to run post-ready; options are (a) add the field and wire it in `load_feature` after `_wire_setup`, or (b) omit it and require nova-w3 wiki phase to keep `_restore_wiki_views` in `client/events.py` as a named import from `doom_bot.wiki`; document the decision in the plan log and in `notes/nova-core.md`.

add `[features]` section to the config TOML model (`nova_core/config.py`): `features_enabled: list[str] = field(default_factory=list)` (parsed from `[features] enabled = [...]`); add `feature_config(name: str) -> dict` method that returns the `[features.<name>]` subtable as a dict, or `{}` if absent. remove the `getattr(config, 'features_enabled', None)` guard added in phase 0; replace with `config.features_enabled`. update `config/attu-bot.sample.toml` with commented `[features]` section. bump `__config_version__` in `nova_core/__init__.py`; adding `[features]` is a TOML format change; nova-w1 phase 4 sets the precedent for bumping on new sections.

silent no-op contract: three cases tested in `test_feature_loader.py`:
1. `ImportError` on unknown name → `WARNING: feature 'x' not found, skipping`
2. module found but no `manifest` attribute → `WARNING: feature 'x' has no manifest, skipping`
3. `manifest` attribute wrong type (not `FeatureManifest`) → `WARNING: feature 'x'.manifest is not a FeatureManifest, skipping`

declaration-order migration guarantee: `load_all` appends each `manifest.migrations` list to a `self._pending_migrations: list` in iteration order; add a `drain_migrations() -> list` method returning the accumulated list and clearing it; add unit test with two synthetic features having distinct migration sentinel values; assert `loader.drain_migrations()` returns `[f1_migration, f2_migration]` in enabled-list order.

repo injection mechanism: implement and document one of the two candidate patterns: (a) loader calls `feature_module.init_repos(db)` after loading the manifest if that function exists on the module; or (b) loader iterates `manifest.repository_classes`, instantiates each with `db`, and sets them via `feature_module._<classname_lower> = instance`; choose the pattern that best matches the existing `_wire_repos()` pattern in `doom_bot/database/__init__.py`; implement `_wire_documents` to run index creation (calling `document_class.ensure_indexes()` or equivalent) and implement the repo injection; document the full pattern in the `nova_core/loader.py` module docstring; add note to `notes/nova-core.md` feature manifest design section.

write the ccboard manifest body (from `notes/nova-core.md` example) as a type-checked test fixture in `tests/python/unit/test_feature_manifest.py`; instantiate the full manifest with mocked classes; assert all fields round-trip; no runtime wiring: import and instantiation only. this fixture validates that the field types are correct for what nova-w3 will actually declare.

**definition of done:**
- `__config_version__` bumped in `nova_core/__init__.py`; `grep '__config_version__' nova_core/__init__.py` shows a version higher than the nova-w1 phase 3 value
- `[features] enabled = [...]` parses from TOML; `config.features_enabled` returns the list; `config.feature_config('eggs')` returns `{}` when no `[features.eggs]` table exists
- `startup` field decision documented in plan log and `notes/nova-core.md`; if included, synthetic test feature exercises it with a no-op coroutine
- ccboard manifest fixture in `test_feature_manifest.py` instantiates without type errors; `basedpyright` passes on the test file
- three silent no-op warning cases tested; all pass
- migration order test: two features with distinct migration sentinels; `loader.drain_migrations()` returns them in `enabled` list order
- repo injection pattern implemented in `_wire_documents`; nova-w3 phase 0 gate "repo injection mechanism confirmed before coding starts" is satisfiable by reading `nova_core/loader.py`
- `docker compose run tests` passes

**cross-phase check:** nova-w3 phase 0 gate: repo injection mechanism is documented and specific enough to implement; read `nova_core/loader.py` module docstring and confirm it names the concrete pattern nova-w3's eggs phase will use.

**merge gate:** phase 0 merged to trunk

---

## phase 2: base package explicit declaration

**status:** open

**scope:**

pre-phase audit (before writing any code): produce a table with 6 rows: one per base item: with columns: name, current implementation location, extraction cost (thin wrapper / minor move / significant move). add the table to the phase log entry. escalate any "significant move" item to the user before continuing; that scope belongs in a separate plan or w3.

define `BASE_PACKAGE: tuple[BasePackageSpec, ...]` in `nova_core/loader.py` with all six items in declaration order:

- **ping**: extract the `command_ping` slash command from its inline decorator in `nova_core/client/__init__.py` into a `_register_ping_command(bot)` function; `BasePackageSpec(name='ping', tasks=[], setup=_register_ping_command)`
- **version**: locate the version command if it exists (grep `slash_command.*version`); if it exists, wire it via setup; if absent, create a stub `BasePackageSpec(name='version', tasks=[], setup=None)` and note in the commit that w3 can fill it in
- **db-backup**: `BasePackageSpec(name='db-backup', tasks=[db_backup_task], setup=None)`: references existing task directly; no code movement
- **error-hook**: `BasePackageSpec(name='error-hook', tasks=[error_hook_task], setup=None)`
- **reload-watcher**: `BasePackageSpec(name='reload-watcher', tasks=[reload_watcher_task], setup=None)`
- **bridge-health**: locate the bridge health check (grep `health` in `nova_core/bridge/`); if it is a task, include in tasks; if it is a startup call or endpoint, use a setup fn; document the actual location in the commit message

update `FeatureContext.load_base()` to iterate `BASE_PACKAGE` in declaration order, calling `_wire_tasks` and `_wire_setup` on each spec. update `_do_ready_init()` to replace `_loader.load_base([])` with `_loader.load_base(BASE_PACKAGE)`.

add a startup sequence comment block at the top of the `_loader.load_base(...)` call in `_do_ready_init()`:

```python
# startup sequence:
#   1. init_database: db connection established
#   2. loader.load_base: base package tasks and commands wired (ping, version, db-backup, error-hook, reload-watcher, bridge-health)
#   3. loader.load_all : feature manifest pass; tasks, events, commands, docs/repos, migrations wired
#   4. register_bot_tasks (shim): hardwired tasks remaining until w3 migrates each feature
#   5. scheduler.start_all: all registered tasks begin running
```

base tasks (db-backup, error-hook, reload-watcher) must not also appear in `register_bot_tasks()` after this phase: check `nova_core/tasks/__init__.py` and remove any duplicate registrations of base tasks that are now wired by `load_base`.

**definition of done:**
- pre-phase audit table produced and committed to plan log before any code is written; no "significant move" items (or they are escalated and approved)
- `nova_core.loader.BASE_PACKAGE` has exactly 6 items; unit test asserts count and name list: `[spec.name for spec in BASE_PACKAGE] == ['ping', 'version', 'db-backup', 'error-hook', 'reload-watcher', 'bridge-health']`
- `grep -n 'load_base\|load_all' nova_core/client/events.py` shows `load_base` before `load_all` inside `_do_ready_init()`
- startup sequence comment block present in `_do_ready_init()`
- base tasks (db-backup, error-hook, reload-watcher) not duplicated in `register_bot_tasks()` after this phase
- `docker compose run tests` passes

**cross-phase check:** nova-w3 can start phases without modifying `nova_core/client/events.py` or `nova_core/loader.py` for base package items: the base pass is complete and requires only `[features].enabled` TOML edits to add or remove non-base features.

**merge gate:** phase 1 merged to trunk

---

## metadata

```yaml
slug: nova-w2
depends_on: [nova-w1]
blocks: [nova-w3]
last_updated: 22 July 2026
```
