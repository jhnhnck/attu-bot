# nova-w5 log

<!-- phase-retro and plan-revise entries appended here in chronological order -->

## cross-plan dependency note — 2026-07-23

**w1/w5: `attu_server/config.py` stubs vs. shared TOML `[[guilds]]` format**

nova-w5 ph0 adds `GuildEntry(id: int, role: str)` and `AuthConfig(api_keys: list[str] = [])` as stubs
on `ServerConfig` in `apps/server/attu_server/config.py`. `load_config` wiring is intentionally deferred:
both fields carry empty defaults.

when nova-w5 adds the `load_config` wiring (reading `raw['guilds']` into `config.guilds` and a
`raw[...]['api_keys']` into `config.auth.api_keys`), the `[[guilds]]` format must match what nova-w1
ph4 defines. gate that wiring on nova-w1 ph4 being closed.

`api_keys` TOML path is nova-w5's to define (nova-w1 does not touch it); suggest `raw['server']['api_keys']`
or a new `[admin]` section.

see `.claude/conflicts.md` for the full conflict record.

## starting phase 0 — 2026-07-24

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w5/`
- branch: `phase/nova-w5`
- parent: `trunk`
- confirmed dod: `GET /admin/ping` returns 200 with valid key, 401 without; `config.auth` and `config.guilds` stubs on `ServerConfig` with empty defaults (no `load_config` wiring — deferred per log note above); admin router in `main.py`; three-case test; `ruff check .` clean; `docker compose run tests` passes

## phase 0 retro — 2026-08-04

**what landed vs spec:**
- all scoped items delivered: `GuildEntry(id, role)` and `AuthConfig(api_keys)` stubs on `ServerConfig`; `require_api_key` dep in `deps.py`; admin router package; `GET /admin/ping`; router mounted at `/api/admin` in `main.py`; three-case unit test.
- `load_config` wiring intentionally deferred per the 2026-07-23 cross-plan note; empty defaults in place. this was planned scope narrowing, not a gap.
- two commits: feat (`9ad69f4`) + fix (`0c31d46`). the fix addressed a test-environment issue, not a code defect.
- 1208 unit + 180 component + 12 attu_logging integration tests pass; 9 pre-existing `test_startup.py` failures (missing config file in worktrees) unchanged.

**what surprised us:**
- `attu_server` was not on the test container's `PYTHONPATH` — new in this plan's worktree setup. the fix commit rewrote the test fixture to build a standalone app directly from the admin router, bypassing `create_app()`'s module-level import side effects. all subsequent admin-router test files must follow this pattern.
- `itsdangerous` was required by `SessionMiddleware` but not declared in `apps/server/pyproject.toml`; discovered during phase 0 and resolved in the fix commit.
- pre-existing architectural oddity surfaced: `apps/server/pyproject.toml` lists only `attu-logging`; all other server runtime deps (fastapi, httpx, tomlkit, uvicorn, itsdangerous) live in `apps/bot/pyproject.toml`. not introduced by this phase — logged in bugs.md for a dep-cleanup pass.

**residual debt:**
- `require_api_key` uses plain `key not in config.auth.api_keys` — not timing-safe; `hmac.compare_digest` should replace it. one-liner fix; deferred from phase 0 scope.
- server dep ownership: `apps/server/pyproject.toml` missing its own runtime deps. pre-existing; deferred.

## revision after phase 0 — 2026-08-04

**phase 1 — revised:** nova-w1 merged to trunk (2026-07-23); the TOML shape is confirmed (`[auth]` → `api_keys`, `[[guilds]]` array). the gate condition from the 2026-07-23 cross-plan note is now satisfied. phase 1 scope expanded to include `load_config` wiring for both `config.auth.api_keys` and `config.guilds`; without this wiring the guild listing endpoints enumerate an always-empty list. timing-safe key comparison (`hmac.compare_digest`) added to phase 1 scope — one-liner, natural home before guild endpoints ship.

**constraints block updated:** added note that admin-router test fixtures must build a standalone app from the router, not call `create_app()`, due to module-level import side effects discovered in phase 0.

**phases 2, 3, 4 — valid:** no premise changes; scope and approach unchanged.
