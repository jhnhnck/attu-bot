# nova-w2 log

## starting phase 0 - 2026-07-24

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

## phase 0 retro - 2026-08-02

### what landed vs spec
- `FeatureManifest` dataclass with all 9 fields and defaults - delivered.
- `FeatureContext` with `load_base`, `load_all`, `load_feature`, and 5 wire helpers - delivered.
- `BASE_PACKAGE = ()` stub and `BasePackageSpec` namedtuple - delivered.
- repo injection pattern documented in `loader.py` module docstring ("registry vs init_repos callback; finalized in phase 1") - delivered.
- `_test_feature` synthetic manifest: run-once task, `on_message` handler, `/manifest-ping` slash command, gated on `test_mode` - delivered.
- 8 new unit tests in `test_feature_loader.py`, all pass; unit 1179/component 180 baselines hold; integration 9 pre-existing errors unchanged.

### what surprised us
- `bot.listen()(fn)` is not the correct pycord 2.x programmatic API; `bot.add_listener(fn, name=event_name)` is confirmed correct. spec listed both as candidates; phase 0 resolved it and documented it in commit 46822eb.
- `features_enabled` is absent from `NovaConfig`; `getattr(config, 'features_enabled', None)` guard required (intentional; phase 1 removes it after adding TOML plumbing).
- startup guard in `events.py` (`try/except Exception` -> `_shutdown(exit_code=1)`) was a non-obvious implementation call; it is correct for a startup-critical path.
- `notes/bugs.md` already had the TZ nit (line 13) from code review. the plan-level `bugs.md` was legitimately empty; both items are mirrored there now for plan-level triage.

### residual debt
- NIT-W2-01: `TZ=UTC`/`_time.tzset()` boilerplate in `test_feature_loader.py:10` - routed to bugs.md, fix-in-phase-1.
- INT-BASELINE-01: 9 pre-existing integration errors in baseline - routed to bugs.md, dispositioned defer.

## revision after phase 0 - 2026-08-02

- phase 1 - full manifest API, TOML feature selection, migration ordering: **valid**. `bot.add_listener` API confirmed by phase 0; `startup` field decision, repo injection implementation, TOML plumbing, and `getattr` guard removal are all correct phase 1 scope. NIT-W2-01 assigned fix-in-phase-1.
- phase 2 - base package explicit declaration: **valid**. `BASE_PACKAGE = ()` stub in place; pre-phase audit requirement and 6-item population scope unchanged.

## starting phase 1 - 2026-08-04

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w2
- branch: phase/nova-w2
- parent sha: 2c86d96 (phase 0 closed)
- decisions made:
  - `startup` field: **omitted**. nova-core.md example has no startup field; `run_once=True, run_immediately=True` task pattern covers post-ready callbacks (demonstrated in `_test_feature`). wiki phase's `_restore_wiki_views` migrates to a run-once task in nova-w3. documented in notes/nova-core.md.
  - repo injection: **pattern (a)** - loader calls `mod.init_repos(db)` if present; feature module owns attribute names and instantiation. documented in `nova_core/loader.py` module docstring and notes/nova-core.md.
- confirmed DoD:
  - `__config_version__` bumped to `2.8.0` in `nova_core/__init__.py` and `config/attu-bot.sample.toml`
  - `config.features_enabled` returns list from TOML `[features] enabled = [...]`
  - `config.feature_config('anything_absent')` returns `{}`
  - ccboard manifest fixture in `test_feature_manifest.py` exists and instantiates cleanly; basedpyright passes on the file
  - three silent no-op warning cases all tested; case 3 message updated to `'is not a FeatureManifest'`
  - `drain_migrations()` test passes: two features with distinct sentinels; order preserved; drain clears list
  - repo injection implemented in `_wire_documents`; `nova_core/loader.py` docstring names the concrete pattern
  - NIT-W2-01 resolved: TZ boilerplate removed from `test_feature_loader.py`
  - ruff passes on all changed files; basedpyright passes on all changed files (pre-existing `RawConfig` TypedDict error not introduced by this phase)
  - 1192 unit tests pass (1 pre-existing failure in `test_start_bot_loop.py` unchanged from baseline)

### what landed vs spec
- `[features]` TOML section added to `NovaConfig`: `features_enabled: list[str]`, `feature_config(name) -> dict`; `RawConfig` TypedDict updated; `_load_from_toml` handles parsing - delivered.
- `getattr(config, 'features_enabled', None)` guard removed from `events.py`; replaced with `config.features_enabled` direct access - delivered.
- `__config_version__` bumped to 2.8.0; `config/attu-bot.sample.toml` updated with commented `[features]` section - delivered.
- `startup` field: omitted - intentional scope narrowing; run-once task pattern covers post-ready callbacks; wiki `_restore_wiki_views` migrates to a run-once task in nova-w3; decision documented in `notes/nova-core.md` - delivered.
- repo injection pattern (a) implemented: `_wire_documents` calls `mod.init_repos(db)` if present; feature module owns instantiation; pattern documented in `nova_core/loader.py` module docstring and `notes/nova-core.md` - delivered.
- `drain_migrations()` method added; collects `manifest.migrations` from each feature in enabled-list order; unit test asserts sentinel ordering - delivered.
- ccboard manifest type-checked fixture in `test_feature_manifest.py` (12 tests); all fields round-trip; basedpyright clean - delivered.
- `test_nova_config_features.py` (7 tests): `feature_config`/`features_enabled` roundtrip; absent-key returns `{}` - delivered.
- NIT-W2-01: `TZ=UTC`/`_time.tzset()` boilerplate removed from `test_feature_loader.py` - resolved per plan.
- test baseline: 1203 unit (24 new), 2 skipped; 180 component unchanged; 9 pre-existing integration errors unchanged.

### what surprised us
- `startup` field resolution was clean: once the run-once task pattern was recognized as covering post-ready callbacks, omitting the field was unambiguous. wiki `_restore_wiki_views` migrates naturally without a new manifest field.
- repo injection pattern (a) vs (b): pattern (a) -- loader calls `mod.init_repos(db)` -- avoids the loader needing to know repository constructor signatures, which vary by feature. aligns with how `doom_bot/database/__init__.py` wires its own repos. pattern (b) would have required loader to introspect constructor arities or use a factory protocol.
- the `getattr` guard removal was entirely mechanical once TOML plumbing landed; no surprises.

### residual debt
- none new. all DoD items met; no items routed to bugs.md.

## revision after phase 1 - 2026-08-04

- phase 2 - base package explicit declaration: **valid**. all phase 1 dependencies satisfied: `BASE_PACKAGE` stub in place (phase 0), `load_base()` implemented (phase 0), `config.features_enabled` direct access in place (phase 1 removes guard). repo injection pattern (a) does not affect phase 2 scope: `BasePackageSpec` items (ping, version, db-backup, error-hook, reload-watcher, bridge-health) are wired via `load_base`, not `load_all`; they do not use `FeatureManifest` or `init_repos`. phase 2 merge gate "phase 1 merged to trunk" is now satisfiable. new unit baseline for phase 2: 1203 pass, 2 skipped; `docker compose run tests` gate should use this as the expected baseline.
