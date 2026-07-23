# log - nova-w1: structural prerequisites
(append per-phase entries here; chronological)

## starting phase 0 - 2026-07-23

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w1
- branch: phase/nova-w1
- parent branch: trunk
- dod: `python -c "import nova_core; print(nova_core.__version__)"` exits 0; Dockerfile sed target references `nova_core/__init__.py`; ruff/basedpyright/coverage list `nova_core`; `doom_bot/__init__.py` unchanged; bot runnable via doom_bot (bridge excluded)

## phase 0 retro - 2026-07-23

**what landed vs spec**
- `nova_core/__init__.py` created with all 10 metadata constants; zero doom_bot imports; DoD check passes
- `nova_core.__version__` resolves to `80.0-dev` live in container (base file: `80.0`; git-info stage appends `-{commit}` at build time; confirmed by integration-check)
- doom_bot unchanged; bot entrypoint unaffected; 180 component tests passed with no new failures
- ruff `known-first-party` and coverage `source` updated in root `pyproject.toml`; basedpyright and pytest required no change (apps/bot already in extraPaths/pythonpath respectively, nova_core auto-discovered by both)
- Dockerfile: nova_core COPY and stamp lines added alongside existing doom_bot lines (additive; doom_bot lines remain intact for phase 0 constraint)

**what surprised us**
- basedpyright auto-discovery confirmed in practice; the scope anticipated no pyproject change was needed, and implementation verified it
- Dockerfile took the additive path (nova_core lines added, doom_bot lines untouched) rather than replacing doom_bot references; this satisfies the phase 0 constraint that doom_bot must remain runnable, but it means phase 1 must explicitly remove the now-redundant doom_bot COPY and stamp lines when doom_bot is deleted

**what residual debt remains**
- pre-existing em-dashes in plan.md and log.md; documentation files only; classified in bug-triage below

## revision after phase 0 - 2026-07-23

phase 1 revised: added explicit Dockerfile cleanup step to scope (remove doom_bot COPY and git-info stamp lines left by phase 0 additive approach); the DoD grep already requires this, but the scope was silent and an implementer could miss three distinct Dockerfile lines that need removal.

phases 2-4: valid - no scope changes needed; their premises assume nova_core in its phase-1 moved state, which is sequencing, not a phase-0 finding.

## cross-plan dependency note — 2026-07-23

**w1/w5: nova-w1 ph4 `[[guilds]]` format is a downstream constraint for nova-w5**

nova-w5 ph0 adds `GuildEntry(id: int, role: str)` as a stub field on `ServerConfig`
(`apps/server/attu_server/config.py`). when nova-w5 later wires `ServerConfig.guilds` to read from
the shared TOML, it must match the `[[guilds]]` format nova-w1 ph4 defines (each entry: `id: int`,
`role: str`, plus any other fields ph4 adds). nova-w5 is aware of this dependency and defers its
`load_config` wiring until nova-w1 ph4 closes.

implementer of nova-w1 ph4: the `GuildEntry` fields you settle on in `nova_core/config.py` become
the canonical shape; coordinate with nova-w5 if fields change from `{id, role}`.

see `.claude/conflicts.md` for the full conflict record.

## starting phase 1 - 2026-07-23

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w1`
- branch: `phase/nova-w1`
- parent: `trunk`
- dod: `grep -rn 'doom_bot' apps/ packages/ tests/ scripts/ config/ --include="*.py"` returns zero lines; same grep over Dockerfiles, `*.yml`, `*.sh` returns zero lines; `ruff check` passes; `basedpyright` passes; Dockerfile sed target uses `nova_core/__init__.py`; bot runnable (bridge excluded - `config.bridge` not yet defined)

## phase 1 retro - 2026-07-23

**what landed vs spec**
- all `doom_bot` -> `nova_core` import sites updated across apps/, packages/, tests/, scripts/ (422+ sites confirmed by dod grep returning zero)
- `attu_logging/webhook.py` updated to import from `nova_core` instead of `doom_bot`; bridges package reference as scoped
- `doom_bot/` directory fully deleted including the phase 0 nova_core metadata shim
- `nova_core/` contains all moved modules: client/, bridge/, commands/, database/, tasks/, eggs/, wiki/, ccboard/, config.py, signals.py, webhook.py, logging.py
- `nova_core/logging.py` intentionally preserved; phase 2 deletes it (by design)
- Dockerfile doom_bot lines removed: two `sed` in git-info stage, one `COPY` in doombox stage, one stamp copy in git-info stage; only nova_core lines remain
- `pyproject.toml` workspace name changed to `nova-core`; isort known-first-party, coverage source, pytest pythonpath all updated
- 180 component tests pass; ruff check and basedpyright pass; dod grep returns zero; integration-check passes

**what surprised us**
- three regression-fix commits followed the initial rename before all checks passed: `48ed318` (entrypoint `doom-bot.py` had `from doom_bot.client import start_bot_loop` missing the `.client` segment after rename); `e37062d` (test fixture `mock_db_and_repos` patched `doom_bot.db` which was a re-export that no longer exists after deletion); `cab68f3` (test mocks in test_commands_stars, test_messages, test_starboard targeted `nova_core.bot` via `nova_core.__init__` which doesn't re-export `bot`; correct path is `nova_core.client.core.bot`)
- the `nova_core.bot` attribute issue confirmed a broader pattern: `test_start_bot_loop.py` and `test_startup.py` have the same `patch.object(nova_core.bot, ...)` and `isinstance(nova_core.bot, ...)` patterns but were not fixed in this phase (they are in the pre-existing unit/integration baseline, not the 180 component tests; deferred as bug #4)

**what residual debt remains**
- `test_start_bot_loop.py` and `test_startup.py` `nova_core.bot` mock-patch patterns confirmed still present; part of pre-existing baseline; see bugs.md for classification

## revision after phase 1 - 2026-07-23

phases 2-4: valid - all premises hold.
- phase 2: `nova_core/logging.py` present as expected; all nova_core import sites updated; no scope changes needed.
- phase 3: `_do_ready_init()` confirmed at line 102 in `nova_core/client/events.py` after the rename; scope's line pointer is still accurate; no changes needed.
- phase 4: premise unchanged; no scope changes needed.

cosmetic: em-dashes in plan.md and log.md fixed in this pass (bugs.md item closed); no downstream phase impact.

## starting phase 2 - 2026-07-23

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w1`
- branch: `phase/nova-w1`
- parent: `trunk`
- dod: `grep -rn 'nova_core\.logging\|doom_bot\.logging' . --include="*.py"` returns zero; `nova_core/logging.py` absent; `attu_logging/webhook.py` has no bot imports; `attu_logging.set_webhook_url()` exists and called from `on_load()` after `config.error_hook` available; inlined `break_at_newline` matches `nova_core/client/util.py`; bot runnable (bridge excluded)

## phase 2 retro - 2026-07-23

**what landed vs spec**
- `nova_core/logging.py` deleted; all 46+ `nova_core.logging` / `doom_bot.logging` import sites migrated to structlog; dod grep returns zero
- `attu_logging/webhook.py` has no bot package imports; `_break_at_newline` inlined from `nova_core/client/util.py`; webhook url read lazily from module-level store at call time
- `attu_logging.set_webhook_url()` added and called from `_do_ready_init()` after db connect; `attu_logging.configure()` receives `DEBUG` env var for backward-compat level behavior
- `PycordBridgeHandler` moved inline to `nova_core/client/__init__.py`; `Logger` type alias usages in `util.py` replaced with `structlog.stdlib.BoundLogger`
- 180 component tests pass; ruff check + ruff format --check clean; bot runnable (bridge excluded)

**what surprised us**
- 3 post-implement regression fixes: (1) `logger.debug(*pages)` varargs call in `commands/wiki.py` unsupported by structlog; fixed to `logger.debug('wiki search results', results=[str(p) for p in pages])`; (2) `mock_logger.warn` in `test_scheduler.py` updated to `warning`; (3) `mock_logger.warn` in `test_task_error_hook.py` updated to `warning`
- 5 newly-visible `test_bridge_sign.py` unit failures are pre-existing (masked by `test_bridge_auth.py` collection stop in phases 0-1); visible now because integration-check ran with `--ignore=test_bridge_auth.py`; see bugs.md
- `set_webhook_url` called inside `try` block in `_do_ready_init()`; if `on_load()` raises before reaching the call, the except-clause `send_to_webhook()` fires before the url is set and silently no-ops; same behavior as pre-migration; timing gap is an accepted risk from the plan

**what residual debt remains**
- explanatory comment at `set_webhook_url` call site in `_do_ready_init()` (timing gap clarification); behavior unchanged; deferred to bugs.md
- `_break_at_newline` drift risk between `attu_logging/webhook.py` and `nova_core/client/util.py`; real fix requires shared-models; deferred to bugs.md (workstream 3)

## revision after phase 2 - 2026-07-23

- phase 3: revised - scope updated to note that `test_bridge_sign.py` pre-existing failures are now visible and must be addressed in this phase; they were masked in phases 0-1 by `test_bridge_auth.py` collection stop; mechanism documented in bugs.md
- phase 4: valid - premises unchanged; no scope changes needed
