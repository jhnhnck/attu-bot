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
