# nova-w2 log

## starting phase 0 — 2026-07-24

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w2
- branch: phase/nova-w2
- parent branch: trunk
- confirmed DoD:
  - `python -c 'from nova_core.manifest import FeatureManifest; m = FeatureManifest(name="x"); print(m.tasks)'` exits 0 printing `[]`
  - `bot.listen()` programmatic pattern confirmed in unit test; fallback to `bot.add_listener()` if needed (noted in commit)
  - `grep -n 'FeatureContext\|load_base\|load_all' nova_core/client/events.py` shows all three calls inside `_do_ready_init()` after `await init_database(...)`
  - `test_feature_loader.py` passes: task wired, event handler registered, setup fn called, unknown feature logs warning, missing manifest attr logs warning
  - `docker compose run tests` passes
  - cross-phase check: no circular imports; `nova_core.manifest` and `nova_core.loader` do not import from feature packages

## phase 0 retro — 2026-08-02

### what landed vs spec
- `FeatureManifest` dataclass with all 9 fields and defaults — delivered.
- `FeatureContext` with `load_base`, `load_all`, `load_feature`, and 5 wire helpers — delivered.
- `BASE_PACKAGE = ()` stub and `BasePackageSpec` namedtuple — delivered.
- repo injection pattern documented in `loader.py` module docstring ("registry vs init_repos callback; finalized in phase 1") — delivered.
- `_test_feature` synthetic manifest: run-once task, `on_message` handler, `/manifest-ping` slash command, gated on `test_mode` — delivered.
- 8 new unit tests in `test_feature_loader.py`, all pass; unit 1179/component 180 baselines hold; integration 9 pre-existing errors unchanged.

### what surprised us
- `bot.listen()(fn)` is not the correct pycord 2.x programmatic API; `bot.add_listener(fn, name=event_name)` is confirmed correct. spec listed both as candidates; phase 0 resolved it and documented it in commit 46822eb.
- `features_enabled` is absent from `NovaConfig`; `getattr(config, 'features_enabled', None)` guard required (intentional; phase 1 removes it after adding TOML plumbing).
- startup guard in `events.py` (`try/except Exception` → `_shutdown(exit_code=1)`) was a non-obvious implementation call; it is correct for a startup-critical path.
- `notes/bugs.md` already had the TZ nit (line 13) from code review. the plan-level `bugs.md` was legitimately empty; both items are mirrored there now for plan-level triage.

### residual debt
- NIT-W2-01: `TZ=UTC`/`_time.tzset()` boilerplate in `test_feature_loader.py:10` — routed to bugs.md, fix-in-phase-1.
- INT-BASELINE-01: 9 pre-existing integration errors in baseline — routed to bugs.md, dispositioned defer.

## revision after phase 0 — 2026-08-02

- phase 1 — full manifest API, TOML feature selection, migration ordering: **valid**. `bot.add_listener` API confirmed by phase 0; `startup` field decision, repo injection implementation, TOML plumbing, and `getattr` guard removal are all correct phase 1 scope. NIT-W2-01 assigned fix-in-phase-1.
- phase 2 — base package explicit declaration: **valid**. `BASE_PACKAGE = ()` stub in place; pre-phase audit requirement and 6-item population scope unchanged.
