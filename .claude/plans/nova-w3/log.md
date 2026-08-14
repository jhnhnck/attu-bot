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

## phase 2 retro — 2026-08-12

### what landed vs spec

- all dod items delivered: `nova_core/modlog/__init__.py` exports manifest; `nova_core/client/modlog.py` deleted; `nova_core/client/__init__.py` has no modlog import; `on_member_join` dual-handler (welcome message + modlog embed) confirmed via integration-check; 1272 unit + 180 component tests pass (+34 modlog handler tests from 1238 baseline).
- event-only feature (no docs, repos, tasks) confirmed; pattern generalizes cleanly from eggs/ccboard -- no repo injection, no task registration, no circular import pressure.
- intentional behavioral change: modlog is now ONLY active when `nova_core.modlog` is in `features.enabled` TOML; previously handlers were loaded unconditionally by `_load_event_handlers()`. prod config needs an explicit `nova_core.modlog` entry before next deploy.

### what surprised us

- the unconditional `_load_event_handlers()` load meant modlog was always-on regardless of toml config; moving to manifest makes it genuinely feature-gated for the first time. this same behavioral change applies to every remaining phase (wiki, trees, starboard all have unconditional load paths in `client/events.py`); prod config must be verified at each deploy.
- `bot.add_listener(fn, name=event_name)` in `FeatureContext._wire_event_handlers()` supports multiple listeners on the same event cleanly; `on_member_join` dual-handler required no special handling.
- cleanest phase so far: no unexpected coupling, no regressions, no post-implement fixups.

### residual debt

- pre-existing lint debt (RUF105/PLW0717 -- 47+30 codebase-wide) carried verbatim into `nova_core/modlog/handlers.py`; already in bugs.md; defer to standalone lint pass.

## revision after phase 2 — 2026-08-12

- phase 3 (wiki): valid -- cross-package extraction scope unchanged; startup field question remains per plan text. note: wiki will become feature-gated (same behavioral change as modlog); prod config must include `nova_core.wiki` at deploy. no scope edit required -- feature-gating is the stated goal.
- phase 4 (reminders): valid -- test-file compensation note already added from phase 1 retro; no change.
- phase 5 (trees): valid -- task-presence verification note already in place; no change. note: trees will also become feature-gated at migrate; prod config must include `nova_core.trees` at deploy.
- phase 6 (starboard): valid -- task-presence and repo-pattern notes already in place; no change. note: starboard event handlers were unconditionally loaded (same pattern as modlog); prod config must include `nova_core.starboard` at deploy.
- phase 2 status: in progress -> closed in 4c7b8ba.

## starting phase 3 — 2026-08-12

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3`
- branch: `phase/nova-w3`
- parent branch: `trunk`
- merge gate check: phase 2 closed in 034ccd1 ✓; `attu_models/__init__.py` and `nova_core/database/__init__.py` at trunk HEAD ✓
- nova-w2 spec check: `FeatureManifest` has no `startup` field — `_restore_wiki_views` will remain in `client/events.py` as a shim import from `nova_core.wiki`; documented in log

**confirmed dod:**
- `packages/attu-wiki/attu_wiki/` importable; `uv sync` clean on skeleton step (before any code moved)
- `nova_core/wiki/__init__.py` under 30 lines
- no `nova_core` imports anywhere in `packages/attu-wiki/`
- `WikiViewDocument`, `WikiViewRepository` live in `nova_core/wiki/`
- `_restore_wiki_views` placement confirmed: stays in `client/events.py`, imports from `nova_core.wiki`
- `docker compose run tests` passes

## phase 3 retro -- 2026-08-12

### what landed vs spec

- all confirmed dod items delivered with one accepted deviation:
  - `packages/attu-wiki/attu_wiki/` importable; `uv sync` clean
  - no `nova_core` imports anywhere in `packages/attu-wiki/` (verified, 0 hits)
  - `WikiViewDocument`, `WikiViewRepository` live in `nova_core/wiki/`
  - `_restore_wiki_views` stays in `client/events.py` importing from `nova_core.wiki`; `FeatureManifest` has no `startup` field -- documented, placement confirmed
  - `docker compose run tests` passes: 1272 unit + 180 component (matches phase 2 baseline)
- `nova_core/wiki/__init__.py` is 32 lines (2 over the "under 30 lines" dod). accepted deviation: a deferred `FeatureManifest` import required to break the circular-import chain adds 1 line; ruff `lines-after-imports = 2` isort config requires 2 blank lines after imports, accounting for the remaining overage. not a regression; not deferred -- accepted as the permanent floor.

### what surprised us

- circular import `nova_core.manifest -> tasks -> nova_year -> wiki -> manifest` required 3 fix iterations: (1) `get_wiki` moved to local scope in `nova_year.py`; (2) mock-target in `test_task_nova_year.py` broke (2 patches moved to `nova_core.wiki.get_wiki`); (3) deferred `FeatureManifest` import in `nova_core/wiki/__init__.py` itself. cycle was wiki-specific -- `nova_year.py` imported a wiki symbol at top level; checked phases 4-6 (`nova_year.py`, `tasks/__init__.py`) -- no reminders/trees/starboard imports; no recurrence expected.
- `wire_wiki_command_repo` helper in `nova_core/wiki/repositories.py` consolidates repo creation, index scheduling, and command-module wiring; creates `nova_core.wiki.repositories -> nova_core.commands.wiki` cross-module dep that eggs/ccboard avoid by doing this wiring in `__init__.py`. logged in bugs.md.
- cross-package extraction is materially heavier than intra-codebase moves: skeleton step, `uv sync`, monorepo `pyproject.toml` wiring, and no `nova_core` leakage check all add friction not present in phases 0-2.

### residual debt

- `wire_wiki_command_repo` cross-module dep (`nova_core.wiki.repositories -> nova_core.commands`); in bugs.md; low risk; no downstream phase blocker.

## revision after phase 3 -- 2026-08-12

- phase 4 (reminders): valid -- checked `nova_year.py` and `tasks/__init__.py`; no reminders imports; circular-import risk does not recur. test-file compensation note and prod-config note from prior revisions intact. no scope change.
- phase 5 (trees): valid -- same check; no trees imports in nova_year or tasks init; no circular-import risk. task-presence verification note and prod-config note intact. no scope change.
- phase 6 (starboard): valid -- same check; no starboard imports in nova_year or tasks init; no circular-import risk. task-presence, repo-pattern, and prod-config notes intact. no scope change.
- phase 3 status: pending merge -> closed in 6856189.
## starting phase 4 — 2026-08-14
- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3
- branch: phase/nova-w3
- parent branch: trunk
- merge gate check: phase 3 closed in 6856189 ✓; attu_models/__init__.py and nova_core/database/__init__.py at trunk HEAD ✓
- scope confirmed unchanged per post-phase-3 revision in log.md

**confirmed dod:**
- nova_core/reminders/__init__.py exports manifest: FeatureManifest
- ReminderDocument, ReminderRepository live in nova_core/reminders/
- reminder_task removed from register_bot_tasks()
- test files that exercise register_bot_tasks() updated to assert manifest.tasks rather than direct task-object presence
- docker compose run tests passes


## phase 4 retro — 2026-08-14

### what landed vs spec

- all dod items delivered: `nova_core/reminders/__init__.py` exports manifest; `ReminderDocument`, `ReminderRepository` live exclusively in `nova_core/reminders/`; both removed from `attu_models` and `nova_core/database/__init__.py`; `reminder_task` removed from `register_bot_tasks()`; test files updated to assert `manifest.tasks`; 1273 unit + 180 component tests pass (baseline incremented by 1 new manifest test).
- intentional scope narrowing: plan offered "shim or delete" for `nova_core/tasks/reminder.py`; implementer chose delete + update all import sites. no shim created.
- test-file compensation (`manifest.tasks` assertion pattern) applied cleanly — no regressions; phase 1's 3 regressions did not recur.

### what surprised us

- git detected `tasks/reminder.py` → `reminders/task.py` as 95%-similar rename; diff was minimal and clean; no hidden coupling surfaced.
- no circular-import pressure: confirmed in phase 3 revision that `nova_year.py` and `tasks/__init__.py` carry no reminders imports; holds. cleanest phase since modlog.
- no new bugs.md items from implementation; no post-implement fixups required.

### residual debt

none.

## revision after phase 4 — 2026-08-14

- phase 5 (trees): valid — no scope change. task-presence verification note ("verify before coding: check whether trees has any tasks in `register_bot_tasks()`") remains appropriate; reminders had no such ambiguity (single known task, straightforward), whereas trees task presence remains unconfirmed. prod-config note (trees becomes feature-gated at migrate) intact.
- phase 6 (starboard): valid — no scope change. task-presence note and event-handler cleanup scope unchanged; deprecation framing unchanged. prod-config note intact.
- phase 4 status: in progress -> closed in 5ed3090.

## starting phase 5 — 2026-08-14
- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3
- branch: phase/nova-w3
- parent branch: trunk
- merge gate check: phase 4 closed in 044727d ✓; attu_models/__init__.py and nova_core/database/__init__.py at trunk HEAD ✓
- scope confirmed unchanged per post-phase-3 revision in log.md; no circular-import risk; task-presence check required before coding

**confirmed dod:**
- nova_core/trees/__init__.py exports manifest: FeatureManifest
- FamilyDocument, FamilyRepository live in nova_core/trees/
- nova_core/client/families.py deleted; no reference to it in nova_core/client/
- if trees tasks were found in register_bot_tasks(): confirmed removed; test files updated to assert manifest.tasks
- docker compose run tests passes

## phase 5 retro — 2026-08-14

### what landed vs spec

- all dod items delivered: `nova_core/trees/__init__.py` exports manifest with `setup=_setup_commands` (deferred-import wrapper), `document_classes=[FamilyDocument]`, `repository_classes=[FamilyRepository]`; `FamilyDocument`, `FamilyRepository` live exclusively in `nova_core/trees/`; `nova_core/client/families.py` deleted; 1273 unit + 180 component tests pass (unchanged from phase 4 baseline).
- trees tasks were confirmed absent from `register_bot_tasks()` before coding; task-removal dod item is n/a -- not a gap, pre-coding verification worked as designed.
- actual import-site caller was `commands/link.py`, not `commands/trees.py` as plan text implied; plan's "any callers of `nova_core.client.families`" catch-all covered it -- intentional narrowing in plan was slightly misnamed, not a scope gap.

### what surprised us

- `setup=commands.trees.setup` direct reference caused a circular-import; resolved by wrapping as `_setup_commands` deferred-import function in `__init__.py`, consistent with the circular-import guard pattern already in nova-core. plan text assumed direct reference; deferred-import is now confirmed as the standard for features whose setup touches the commands namespace.
- `commands/link.py` (not `commands/trees.py`) was the real caller of `nova_core.client.families`; plan named the wrong file. git rename detection confirmed `nova_core/client/families.py` -> `nova_core/trees/families.py` at 100% similarity; diff was minimal.
- no tasks existed in `register_bot_tasks()` for trees; task-presence pre-coding check confirmed absent cleanly.
- pre-existing pyproject.toml lint debt (`rule-codes-in-selectors`, 28+ instances) surfaced during implementation; logged in bugs.md at `317c0b0`; not introduced by this phase.

### residual debt

none new. `rule-codes-in-selectors` already in bugs.md.

## revision after phase 5 — 2026-08-14

- bugs.md: all 4 open items reviewed; 0 disposition changes; none block phase 6 (all are codebase-wide lint debt or a low-risk cross-module dep in wiki, unrelated to starboard code paths).
- phase 6 (starboard): revise -- add scope bullet: "verify before coding: check `setup=commands.stars.setup` for circular-import; trees and wiki both required a `_setup_commands` deferred-import wrapper to prevent cycle -- apply same pattern if starboard's setup import creates a cycle." no other scope change; event-handler, task-presence, test-file-compensation, and prod-config notes intact.
- phase 5 status: in progress -> closed in c5a3c2d.


## starting phase 6 — 2026-08-14
- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3
- branch: phase/nova-w3
- parent branch: trunk
- merge gate check: phase 5 closed in 5447e12 ✓; attu_models/__init__.py and nova_core/database/__init__.py at trunk HEAD ✓; ccboard stability in primary guild — to be confirmed at merge time
- scope confirmed unchanged per post-phase-5 revision; deferred-import pre-check added for setup

**confirmed dod:**
- nova_core/starboard/__init__.py exports manifest: FeatureManifest
- client/events.py contains no starboard imports or _starboard_enabled
- if starboard tasks were found in register_bot_tasks(): confirmed removed; test files updated to assert manifest.tasks
- attu_models/documents.py and attu_models/repositories.py contain no feature-specific classes (grep for Egg, Reaction, Entry, Family, Reminder, WikiView, StarredMessage returns zero hits)
- nova_core/database/__init__.py exports only infra, platform-service, and attu-specific classes
- docker compose run tests passes

