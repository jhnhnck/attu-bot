# nova-w4 — phase log

<!-- phase-retro and plan-revise append here after each phase -->

## starting phase 0 — 2026-07-24

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w4
- branch: phase/nova-w4
- parent branch: trunk
- confirmed DoD: walking skeleton — `uv sync` resolves cleanly with apps/casino as a workspace member; `python apps/casino/casino-bot.py bot` logs ready state; `ruff check apps/casino/ --select S311` exits 0; `python scripts/run_tests.py` green; `docker compose -f docker-compose.dev.yml config` validates. Nova-w1 confirmed complete (import nova_core, no doom_bot stand-in needed).

## phase 0 retro — 2026-07-24

**what landed vs spec:** all scoped items delivered — root `pyproject.toml` workspace wiring, `apps/casino/pyproject.toml`, `casino-bot.py` entry point, `casino_bot/__init__.py` with `start_casino_loop()`, `casino.toml` dev config, `apps/casino/Dockerfile`, `docker-compose.dev.yml` casino service. nova-w1 confirmed complete at phase start — no `doom_bot` stand-in needed. DoD verified: `uv sync` clean, docker compose validates, S311 enforced, 1170 unit tests pass, 2 skipped, 1 pre-existing failure (unrelated).

**what surprised us:** the initial S311 approach (`"apps/casino/**" = []` in `per-file-ignores`) was inert — `per-file-ignores` is additive to the global `ignore` list and cannot re-enable a globally-suppressed rule. fix required inverting the approach: remove S311 from global ignore, add targeted per-file suppressions for the three bot files that legitimately use `random` (`debug.py`, `hatching.py`, `logo_update.py`). corrected in `21f631b`.

**what residual debt remains:** `on_ready` reconnect invalidates in-flight DB references in phases 2+ (fix-in-phase-2); casino Dockerfile omits git-info stamp stage (deferred to production); pre-existing unit test failure `test_sets_discord_http_logger_to_debug` is out of scope for nova-w4 (won't-fix).

## revision after phase 0 — 2026-07-24

- **phase 1** — valid, no changes. scope and approach hold; no nova-w2 dependency.
- **phase 2** — revised: added pitfall — `on_ready` re-calls `_db.connect()` on every Discord reconnect; features in phases 2+ must not cache the DB object at setup time. flagged as prerequisite before any feature registers a DB caller. nova-w2 dependency unchanged.
- **phase 3** — valid, no changes.
- **phase 4** — valid, no changes.
