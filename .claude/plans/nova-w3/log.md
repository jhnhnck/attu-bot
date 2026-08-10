# log — nova-w3

(append per-phase entries here; chronological)

## starting phase 0 — 2026-08-10

- worktree: `/home/jhn/Projects/doom-bot/.claude/worktrees/nova-w3`
- branch: `phase/nova-w3`
- parent branch: `trunk`
- confirmed dod:
  - repo injection pattern confirmed: loader calls `mod.init_repos(db)` after loading manifest (nova-core.md)
  - `doom_bot/eggs/__init__.py` exports `manifest: FeatureManifest`
  - `EggDocument`, `EggUserDocument`, `EggRepository`, `EggUserRepository` importable only from `nova_core.eggs.*`
  - `register_bot_tasks()` contains no reference to eggs tasks
  - with eggs removed from toml `[features].enabled`, bot starts without egg repos wired
  - `docker compose run tests` passes; `ruff check .` clean
