# nova-w5 bugs

## open

- **bridge fix endpoint missing:** `POST /bridge/fix/recalculate-starboard` does not exist in `doom_bot/bridge/router.py`. the `fix.py` admin endpoint ships with a `501` fallback until this lands. tracked here so `bug-triage` can promote it to a real bridge task when phase 3 merges. severity: medium (feature incomplete, not broken). disposition: deferred to nova-w3 or a standalone bridge task.

- **worktree `.secrets/attu-bot.toml` junk directory:** docker creates an empty directory at `.secrets/attu-bot.toml` (owned by root) when the worktree lacks the secrets file. this blocks component and integration tests when running `docker compose` from the worktree. workaround: `sudo rm -rf .secrets && mkdir .secrets && ln -sf /home/jhn/Projects/doom-bot/.secrets/attu-bot.toml .secrets/attu-bot.toml`. does not affect unit tests. severity: low (unit tests are the primary gate for worktree development). disposition: defer; does not block any phase, unit tests unaffected.

- **server dep ownership:** `apps/server/pyproject.toml` declares only `attu-logging`; all other server runtime deps (fastapi, httpx, tomlkit, uvicorn, itsdangerous) live in `apps/bot/pyproject.toml`. pre-existing architectural oddity surfaced during phase 0 test-container work. severity: low (uv workspace resolves transitively; no runtime failures). disposition: defer; cleanup-bridge or a standalone dep-ownership pass.

## closed

- **`require_api_key` uses plain string comparison:** fixed in phase 1 (da22118); `hmac.compare_digest` with any-match logic now used in `deps.py`.
