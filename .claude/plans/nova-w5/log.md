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
