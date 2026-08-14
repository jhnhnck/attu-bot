# nova-w3 — feature migration

## goals

1. each migrated feature (eggs, ccboard, modlog, wiki, reminders, trees, starboard) owns its document and repository classes; `attu_models` retains only infra, platform-service, and attu-specific classes after all phases close
2. each feature declares a `FeatureManifest` in its `__init__.py`; the nova-w2 loader wires tasks, events, commands, and document/repo registration without editing core files
3. wiki client code extracted to `packages/attu-wiki/attu_wiki/`; `WikiClient.__init__` gains `user_agent: str` param; bot shim `nova_core/wiki/__init__.py` stays under 30 lines
4. modlog extracted from `nova_core/client/modlog.py` into a new `nova_core/modlog/` feature package with manifest
5. after phase 0 closes, adding or removing a feature requires only a toml edit — no changes to `nova_core/tasks/__init__.py` or `nova_core/client/events.py`

## non-goals

- `doom_bot` → `nova_core` package rename (nova-w1)
- `FeatureManifest` class and loader implementation (nova-w2)
- `attu_logging` migration (nova-w1)
- casino features (nova-w4); admin repl (nova-w5)
- attu-specific feature migration: timekeeping (`nova_year`), markers, year links
- logo-update task migration (deferred)

## constraints

- nova-w2 must be closed before phase 0 coding starts (`FeatureManifest`, `FeatureContext`, loader live in `client/events.py on_ready`)
- nova-w1 must be closed before phase 0 coding starts (`doom_bot.logging` deleted, all 46 call sites on `structlog`)
- phases are strictly sequential; `attu_models/documents.py`, `attu_models/repositories.py`, and `nova_core/database/__init__.py` are touched in every phase — parallel branches will conflict
- `docker compose run tests` must pass at every phase merge
- no push without explicit instruction

## accepted risks

three risks named in `pre-mortem.md` are accepted going in. first: the repo injection mechanism (how the nova-w2 loader wires feature repo singletons) is unspecified here and must be confirmed against the nova-w2 spec before phase 0 coding starts; if the injection pattern differs from the current `_wire_repos()` approach, phase 0 scope will need adjustment. second: `_restore_wiki_views` is a startup hook, not a Discord event; it may not fit the `event_handlers` dict cleanly — phase 3 will verify against the nova-w2 spec and either use a `startup` field if one exists or keep the restore logic in `client/events.py` as a shim import. third: the `FeatureManifest.migrations` field is assumed to be implemented by nova-w2 for phase 1 (ccboard has `migration.py`); if it isn't, phase 1 notes this and leaves migration wiring unchanged. all other risks are low and noted in their respective phases.

---

### phase 0 — eggs (walking skeleton)

**status:** pending merge

**scope:** eggs is the template phase. it proves the full migration pattern end-to-end before any other feature is touched.

- move `EggDocument`, `EggUserDocument` from `attu_models/documents.py` to `doom_bot/eggs/documents.py`
- move `EggRepository`, `EggUserRepository` from `attu_models/repositories.py` to `doom_bot/eggs/repositories.py`
- remove eggs classes from `attu_models/documents.py`, `attu_models/repositories.py`, `attu_models/__init__.py`
- remove eggs repos from `doom_bot/database/__init__.py` `_wire_repos()` and `init_database()`; remove eggs exports from `__all__`
- update import sites: `commands/eggs.py`, `tasks/egg_cleanup.py`, `tasks/presence.py`, `eggs/hatching.py`
- declare `manifest` in `doom_bot/eggs/__init__.py`: `tasks=[egg_cleanup_task, presence_update_task]`, `setup=commands.eggs.setup`, `document_classes=[EggDocument, EggUserDocument]`, `repository_classes=[EggRepository, EggUserRepository]`
- remove `egg_cleanup_task` and `presence_update_task` from `tasks/__init__.py register_bot_tasks()`
- clean up any `doom_bot.logging` remnants in eggs files (nova-w1 should have handled these; fix stragglers here)

**dod:**
- nova-w2 repo injection mechanism documented and confirmed before coding starts (pre-mortem high risk)
- `doom_bot/eggs/__init__.py` exports `manifest: FeatureManifest`
- `EggDocument`, `EggUserDocument`, `EggRepository`, `EggUserRepository` importable only from `doom_bot.eggs.*`
- `register_bot_tasks()` contains no reference to eggs tasks
- with eggs removed from toml `[features].enabled`, the bot starts without `_egg_repo`/`_egg_user_repo` wired and no eggs index init runs (confirm via startup log)
- `docker compose run tests` passes; `ruff check .` clean

**merge gate:** nova-w1 closed (doom_bot.logging deleted); nova-w2 closed (FeatureManifest, FeatureContext, loader wired in client/events.py on_ready)

---

### phase 1 — ccboard

**status:** open

**scope:** ccboard is the highest-complexity feature: asyncio lock registry, pending-removal set, four reaction events, an existing `migration.py`, and the `ccboard.enabled` per-guild feature flag.

- move `ReactionDocument`, `BoardEntryDocument` to `nova_core/ccboard/documents.py`
- move `ReactionRepository`, `EntryRepository` to `nova_core/ccboard/repositories.py`
- remove from `attu_models` and `nova_core/database/__init__.py`
- update all import sites in `ccboard/` modules and `commands/cc_stars.py`
- declare `manifest` in `nova_core/ccboard/__init__.py`: `tasks=[manager_task, auditor_task]`, `event_handlers={'on_raw_reaction_add': ..., 'on_raw_reaction_remove': ..., 'on_raw_reaction_clear': ..., 'on_raw_reaction_clear_emoji': ...}`, `setup=commands.cc_stars.setup`, `guild_config_key='ccboard'`, `guild_config_model=GuildCCBoard`, `document_classes`, `repository_classes`, `migrations=[...]` (confirm migrations field exists in nova-w2 spec; if not, skip and note)
- remove ccboard event handlers and `_ccboard_enabled` from `client/events.py`
- remove `ccboard_manager_task`, `ccboard_auditor_task` from `register_bot_tasks()`

**dod:**
- `nova_core/ccboard/__init__.py` exports `manifest: FeatureManifest`
- `client/events.py` contains no ccboard imports or `_ccboard_enabled`
- `register_bot_tasks()` contains no reference to ccboard tasks
- with ccboard removed from toml `[features].enabled`, no ccboard event handlers fire (confirm via startup log — no ccboard registration output)
- `FeatureManifest.migrations` field handling confirmed against nova-w2 spec before coding starts
- `docker compose run tests` passes

**merge gate:** phase 0 closed on trunk; `attu_models/__init__.py` and `nova_core/database/__init__.py` are at trunk HEAD before coding starts

---

### phase 2 — modlog

**status:** open

**scope:** modlog has no documents or repos — pure event handlers only. this phase proves the manifest works for event-only features and validates extracting code from `client/` into a new feature package.

- create `nova_core/modlog/__init__.py` and `nova_core/modlog/handlers.py`
- move all event handler functions from `nova_core/client/modlog.py` to `nova_core/modlog/handlers.py`
- declare `manifest` in `nova_core/modlog/__init__.py`: `event_handlers={'on_member_join': ..., 'on_member_remove': ..., 'on_member_ban': ..., 'on_member_unban': ..., 'on_guild_channel_create': ..., 'on_guild_channel_delete': ..., 'on_guild_channel_update': ..., 'on_guild_role_create': ..., 'on_guild_role_delete': ..., 'on_guild_role_update': ..., 'on_member_update': ..., 'on_guild_emojis_update': ...}`; no tasks, no commands, no documents
- remove `importlib.import_module('nova_core.client.modlog')` from `nova_core/client/__init__.py`
- delete `nova_core/client/modlog.py`
- note: `on_member_join` will have two active handlers after this phase (welcome message stays in `client/events.py`; modlog embed moves to manifest); both must fire — pycord supports multiple `bot.listen()` registrations on the same event

**dod:**
- `nova_core/modlog/__init__.py` exports `manifest: FeatureManifest`
- `nova_core/client/modlog.py` deleted; `nova_core/client/__init__.py` has no modlog import
- `on_member_join` fires both welcome message (events.py) and modlog embed (manifest handler) — confirmed in tests or startup smoke
- `docker compose run tests` passes

**merge gate:** phase 1 closed on trunk; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD

---

### phase 3 — wiki (package extraction)

**status:** open

**scope:** wiki is the only cross-workspace package extraction in nova-w3. `packages/attu-wiki/` must build and sync independently before any code moves.

**step 1 (walking skeleton — do not proceed past this until `uv sync` passes):**
- create `packages/attu-wiki/attu_wiki/__init__.py` (empty) and `packages/attu-wiki/pyproject.toml`
- list all third-party deps from `nova_core/wiki/client.py` and siblings in `pyproject.toml` (e.g. `httpx`, `aiohttp` — check actual imports first)
- add `attu-wiki` to `apps/bot/pyproject.toml` and root `[tool.uv.workspace]`
- run `uv sync`; confirm importable before moving any code

**step 2 (code move):**
- move `auth.py`, `pages.py`, `search.py`, `admin.py`, `models.py`, `client.py` from `nova_core/wiki/` to `packages/attu-wiki/attu_wiki/`
- `WikiClient.__init__` gains `user_agent: str` param; removes `nova_core.__email__/__title__/__version__` imports (package is `nova_core`; remove metadata imports if any remain)
- all moved modules: replace any remaining `doom_bot.logging` with `structlog.stdlib.get_logger(__name__)`; no `nova_core` imports anywhere in `packages/attu-wiki/`
- bot shim `nova_core/wiki/__init__.py`: constructs `user_agent` from bot metadata; `get_wiki()` singleton remains; `setup(bot)` remains; under 30 lines total
- move `WikiViewDocument` to `nova_core/wiki/documents.py`; `WikiViewRepository` to `nova_core/wiki/repositories.py`
- remove `WikiViewDocument`, `WikiViewRepository` from `attu_models`; remove from `nova_core/database/__init__.py`
- update import sites in `commands/wiki.py` and `client/events.py` (`_restore_wiki_views`)
- `_restore_wiki_views` startup hook: check nova-w2 spec for a `startup` field on `FeatureManifest`; if present, move restore logic into manifest; if absent, keep `_restore_wiki_views` in `client/events.py` and import from `nova_core.wiki` — document the choice in phase log
- declare `manifest` in `nova_core/wiki/__init__.py`: `setup=commands.wiki.setup`, `startup=_restore_wiki_views` (if supported) or note omission, `document_classes=[WikiViewDocument]`, `repository_classes=[WikiViewRepository]`

**dod:**
- `packages/attu-wiki/attu_wiki/` importable; `uv sync` clean on clean virtualenv after skeleton step (before any code moved)
- `nova_core/wiki/__init__.py` under 30 lines
- no `nova_core` imports anywhere in `packages/attu-wiki/`
- `WikiViewDocument`, `WikiViewRepository` live in `nova_core/wiki/`
- `_restore_wiki_views` startup hook placement confirmed and documented
- `docker compose run tests` passes

**merge gate:** phase 2 closed on trunk; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD; nova-w2 spec checked for `startup` manifest field before coding starts

---

### phase 4 — reminders

**status:** open

**scope:** straightforward data + task migration. proves the pattern on an attu-specific feature (in-universe haracalnde calendar system).

- create `nova_core/reminders/` package
- move `ReminderDocument` to `nova_core/reminders/documents.py`
- move `ReminderRepository` to `nova_core/reminders/repositories.py`
- move `nova_core/tasks/reminder.py` logic into `nova_core/reminders/task.py`; update `nova_core/tasks/reminder.py` as thin re-export shim or delete and update import sites
- declare `manifest` in `nova_core/reminders/__init__.py`: `tasks=[reminder_task]`, `setup=commands.remind.setup`, `document_classes=[ReminderDocument]`, `repository_classes=[ReminderRepository]`
- remove `ReminderDocument`, `ReminderRepository` from `attu_models`; remove from `nova_core/database/__init__.py`
- remove `reminder_task` from `register_bot_tasks()`

**dod:**
- `nova_core/reminders/__init__.py` exports `manifest: FeatureManifest`
- `ReminderDocument`, `ReminderRepository` live in `nova_core/reminders/`
- `reminder_task` removed from `register_bot_tasks()`
- test files that exercise `register_bot_tasks()` updated to assert `manifest.tasks` rather than direct task-object presence (phase 1 had 3 regressions from this pattern)
- `docker compose run tests` passes

**merge gate:** phase 3 closed on trunk; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD

---

### phase 5 — trees

**status:** open

**scope:** commands-only feature. also validates moving a `client/` helper file into the feature package.

- verify before coding: check whether trees has any tasks currently in `register_bot_tasks()`; if yes, add `tasks=[...]` to manifest declaration and add task-removal dod item below
- create `nova_core/trees/` package
- move `FamilyDocument` to `nova_core/trees/documents.py`
- move `FamilyRepository` to `nova_core/trees/repositories.py`
- move `nova_core/client/families.py` to `nova_core/trees/families.py`; update any internal imports
- declare `manifest` in `nova_core/trees/__init__.py`: `setup=commands.trees.setup`, `document_classes=[FamilyDocument]`, `repository_classes=[FamilyRepository]`, plus `tasks=[...]` if confirmed above
- remove `FamilyDocument`, `FamilyRepository` from `attu_models`; remove from `nova_core/database/__init__.py`
- update all import sites (`commands/trees.py` and any callers of `nova_core.client.families`)

**dod:**
- `nova_core/trees/__init__.py` exports `manifest: FeatureManifest`
- `FamilyDocument`, `FamilyRepository` live in `nova_core/trees/`
- `nova_core/client/families.py` deleted; no reference to it in `nova_core/client/`
- if trees tasks were found in `register_bot_tasks()`: confirmed removed; test files updated to assert `manifest.tasks` rather than direct task-object presence
- `docker compose run tests` passes

**merge gate:** phase 4 closed on trunk; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD

---

### phase 6 — starboard

**status:** open

**scope:** starboard is deprecated and will be removed when ccboard is confirmed stable. this phase migrates it into manifest form so it can be removed by a toml edit alone. the removal (delete package, remove from toml) is not in this phase's scope.

- move `StarredMessageDocument` to `nova_core/starboard/documents.py`
- move `StarboardRepository` to `nova_core/starboard/repositories.py`
- move `nova_core/client/starboard.py` to `nova_core/starboard/handlers.py`; update internal imports
- verify before coding: check whether starboard has any tasks currently in `register_bot_tasks()`; if yes, add `tasks=[...]` to manifest declaration and add task-removal dod item below
- verify before coding: check `setup=commands.stars.setup` for circular-import; trees and wiki both required a `_setup_commands` deferred-import wrapper to prevent a cycle -- apply same pattern if starboard's setup import creates a cycle
- declare `manifest` in `nova_core/starboard/__init__.py`: `event_handlers={'on_raw_reaction_add': ..., 'on_raw_reaction_remove': ..., 'on_raw_reaction_clear': ..., 'on_raw_reaction_clear_emoji': ...}`, `setup=commands.stars.setup`, `guild_config_key='starboard'`, `guild_config_model=GuildStarboard`, `document_classes=[StarredMessageDocument]`, `repository_classes=[StarboardRepository]`, plus `tasks=[...]` if confirmed above
- remove starboard event handlers and `_starboard_enabled` from `client/events.py`
- remove `StarredMessageDocument`, `StarboardRepository` from `attu_models`; remove from `nova_core/database/__init__.py`

**dod:**
- `nova_core/starboard/__init__.py` exports `manifest: FeatureManifest`
- `client/events.py` contains no starboard imports or `_starboard_enabled`
- if starboard tasks were found in `register_bot_tasks()`: confirmed removed; test files updated to assert `manifest.tasks` rather than direct task-object presence
- `attu_models/documents.py` and `attu_models/repositories.py` contain no feature-specific classes: grep for `Egg`, `Reaction`, `Entry`, `Family`, `Reminder`, `WikiView`, `StarredMessage` returns zero hits
- `nova_core/database/__init__.py` exports only infra, platform-service, and attu-specific classes
- `docker compose run tests` passes

**merge gate:** phase 5 closed on trunk; ccboard confirmed stable in primary guild; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD

---

## status

| phase | status |
|---|---|
| 0 — eggs (walking skeleton) | closed in bd29d87 |
| 1 — ccboard | closed in 6964bc4 |
| 2 — modlog | closed in 034ccd1 |
| 3 — wiki (package extraction) | closed in 6856189 |
| 4 — reminders | closed in 044727d |
| 5 — trees | closed in 5447e12 |
| 6 — starboard | in progress |

---

## metadata

```yaml
slug: nova-w3
depends_on: [nova-w1, nova-w2]
last_updated: 22 July 2026
```
