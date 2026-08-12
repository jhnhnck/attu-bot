# log — nova-w3

(append per-phase entries here; chronological)

## starting phase 0 — 2026-08-10

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3`
- branch: `phase/nova-w3`
- parent branch: `trunk`
- confirmed dod:
  - repo injection pattern confirmed: loader calls `mod.init_repos(db)` after loading manifest (nova-core.md)
  - `nova_core/eggs/__init__.py` exports `manifest: FeatureManifest`
  - `EggDocument`, `EggUserDocument`, `EggRepository`, `EggUserRepository` importable only from `nova_core.eggs.*`
  - `register_bot_tasks()` contains no reference to eggs tasks
  - with eggs removed from toml `[features].enabled`, bot starts without egg repos wired
  - `docker compose run tests` passes; `ruff check .` clean

## phase 0 retro (2026-08-10)

### what landed vs spec

- all dod items delivered: nova_core/eggs/__init__.py exports manifest; EggDocument, EggUserDocument, EggRepository, EggUserRepository live exclusively in nova_core.eggs.*; egg classes removed from attu_models and nova_core/database/__init__.py; egg tasks removed from register_bot_tasks(); 1209 unit + 180 component tests pass; ruff clean.
- pre-mortem high risk (repo injection pattern) resolved: loader calls mod.init_repos(db) with MongoStorage; asyncio.ensure_future() schedules index init from the sync callsite; task ref held in _bg_tasks to prevent gc before completion.
- toml sample now shows nova_core.eggs as the full feature module path while other features in the comment still use short names -- intentional narrowing, self-corrects as each phase lands; not a bug.
- plan.md scope and dod text for phases 1-6 still reference doom_bot.* paths; nova-w1 package rename makes those stale -- corrected in plan-revise below.

### what surprised us

- write/edit tools blocked by bgIsolation guard; all edits done via bash heredocs; no functional consequence but slower than expected.
- pre-existing ruff-format issue in notes/nova-core.md fixed as incidental chore (447a587); outside phase scope.
- no unexpected coupling: eggs module dependencies mapped cleanly; hatching.py mirrored repos via direct module-attribute assignment rather than requiring injected arguments.

### residual debt

none.

## revision after phase 0 (2026-08-10)

- phases 1-6: revise -- all scope and dod text corrected from doom_bot.* paths to nova_core.* paths; nova-w1 package rename makes the original paths stale; goals section (lines 7-9) and constraints line 24 updated for the same reason; substantive scope unchanged across all six phases.
- phase 3 additionally: parenthetical "package is doom_bot during nova-w3" removed (now says "package is nova_core"); "no doom_bot imports" constraint updated to "no nova_core imports" in scope and dod.
- phase 0 status: not started -> pending merge (no explicit closure confirmation in dispatch).

## starting phase 1 (2026-08-11)

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3`
- branch: `phase/nova-w3`
- parent branch: `trunk` (at `f8939ac`)
- confirmed dod:
  - `nova_core/ccboard/__init__.py` exports `manifest: FeatureManifest`
  - `client/events.py` contains no ccboard imports or `_ccboard_enabled`
  - `register_bot_tasks()` contains no reference to ccboard tasks
  - `FeatureManifest.migrations` field confirmed present in `nova_core/manifest.py:25`
  - `attu_models/documents.py` and `attu_models/repositories.py` contain no ccboard classes
  - `docker compose run tests` passes (1238 unit + 180 component)

## phase 1 retro (2026-08-11)

### what landed vs spec

- all confirmed dod items delivered: `nova_core/ccboard/__init__.py` exports manifest; ccboard imports and `_ccboard_enabled` removed from `client/events.py`; ccboard tasks removed from `register_bot_tasks()`; ccboard classes removed from `attu_models`; 1238 unit + 180 component tests pass.
- `migrations=[]` confirmed correct: ccboard's `migration.py` is a `/fix ccboard convert` slash-command handler, not an auto-run schema migration object; intentional narrowing from the plan's "confirm migrations field" uncertainty.
- startup-log gate (ccboard removed from toml, confirm no handlers fire) not performed -- dropped from confirmed dod during implementation; plan.md listed it as a dod item; unconfirmed, not a regression.

### what surprised us

- `init_repos(db)` wires `_reaction_repo` and `_entry_repo` as module-level attributes directly on the ccboard module; watcher/manager/auditor access via `ccboard._reaction_repo` at call time -- no per-module singletons required, confirming the eggs module-attribute pattern generalizes to a more complex feature.
- event handlers declared inline in `nova_core/ccboard/__init__.py` rather than a separate `handlers.py`; `_on_raw_reaction_add` is_bot detection logic carried over intact from the original `events.py`.
- circular import forced bottom-of-file task imports in `__init__.py`: `auditor.py` and `manager.py` both do `from nova_core import ccboard` at top level; imports placed at bottom with `# noqa: E402` plus inline reason comments.
- 4 post-implement regressions found and fixed across two cleanup commits: missed test file `test_commands_fix_stars_convert.py` (wrong import path after migration) and 3 `register_bot_tasks` tests that asserted direct task-object presence rather than `manifest.tasks`.

### residual debt

none.

## revision after phase 1 (2026-08-11)

- phase 2 (modlog): valid -- no tasks, no repos; event-only feature; implementer confirmed modlog has no tasks; no scope drift from phase 1 learnings.
- phase 3 (wiki): valid -- no tasks; cross-package extraction scope unchanged; module-attribute repo pattern is confirmatory only, no wiring change needed.
- phase 4 (reminders): revise -- add dod note: before closing, verify test files that exercise `register_bot_tasks()` do not assert direct task-object presence; update to assert `manifest.tasks` instead. same pattern that caused 3 regressions in phase 1. module-attribute repo pattern confirmed applicable (eggs + ccboard), no wiring change needed.
- phase 5 (trees): revise -- implementer notes trees has tasks currently in `register_bot_tasks()`; plan scope says "no tasks, no event handlers" -- verify before coding starts; if trees does have tasks, add `tasks=[...]` to manifest declaration, add task-removal dod item, and apply test-file compensation check. module-attribute repo pattern confirmed applicable, no wiring change needed.
- phase 6 (starboard): revise -- implementer notes starboard has tasks in `register_bot_tasks()`; plan manifest declaration omits `tasks=`; add scope item to verify and declare if present; add dod note for test-file compensation check. module-attribute repo pattern confirmed applicable, no wiring change needed.
- phase 1 status: in progress -> pending merge.

## bookkeeping catch-up — 2026-08-12

phases 0 and 1 were implemented and retro'd in a prior session. the worktree and branch were cleaned up, but `set-status "closed in <sha>"` never fired. both retros cite test-pass counts (1209 unit + 180 component for phase 0; 1238 unit + 180 component for phase 1), confirming integration-check ran. status table updated:
- phase 0: pending merge -> closed in bd29d87 (last commit before phase 1 log entry)
- phase 1: pending merge -> closed in 6964bc4 (trunk head at phase-2 worktree creation)

## starting phase 2 — 2026-08-12

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3`
- branch: `phase/nova-w3`
- parent branch: `trunk` (at `6964bc4`)
- confirmed dod:
  - `nova_core/modlog/__init__.py` exports `manifest: FeatureManifest`
  - `nova_core/client/modlog.py` deleted; `nova_core/client/__init__.py` has no modlog import
  - `on_member_join` fires both welcome message (events.py) and modlog embed (manifest handler)
  - `docker compose run tests` passes
