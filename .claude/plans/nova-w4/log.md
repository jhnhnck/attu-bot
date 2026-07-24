# nova-w4 — phase log

<!-- phase-retro and plan-revise append here after each phase -->

## starting phase 0 — 2026-07-24

- worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/nova-w4
- branch: phase/nova-w4
- parent branch: trunk
- confirmed DoD: walking skeleton — `uv sync` resolves cleanly with apps/casino as a workspace member; `python apps/casino/casino-bot.py bot` logs ready state; `ruff check apps/casino/ --select S311` exits 0; `python scripts/run_tests.py` green; `docker compose -f docker-compose.dev.yml config` validates. Nova-w1 confirmed complete (import nova_core, no doom_bot stand-in needed).
