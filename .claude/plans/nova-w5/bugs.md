# nova-w5 bugs

## open

- **bridge fix endpoint missing** — `POST /bridge/fix/recalculate-starboard` does not exist in `doom_bot/bridge/router.py`. the `fix.py` admin endpoint ships with a `501` fallback until this lands. tracked here so `bug-triage` can promote it to a real bridge task when phase 3 merges. severity: medium (feature incomplete, not broken). disposition: deferred to nova-w3 or a standalone bridge task.

- **`require_api_key` uses plain string comparison** — `key not in config.auth.api_keys` is not timing-safe; a timing attack could distinguish between a valid and invalid api key. `hmac.compare_digest` should be used instead. severity: low (api keys are long-lived secrets, not session tokens; brute-force mitigations belong at the reverse-proxy layer). disposition: fix-in-phase-1 — one-liner; phase 1 is the natural place before guild endpoints ship behind the same gate.

- **worktree `.secrets/attu-bot.toml` junk directory** — docker creates an empty directory at `.secrets/attu-bot.toml` (owned by root) when the worktree lacks the secrets file. this blocks component and integration tests when running `docker compose` from the worktree. workaround: `sudo rm -rf .secrets && mkdir .secrets && ln -sf /home/jhn/Projects/doom-bot/.secrets/attu-bot.toml .secrets/attu-bot.toml`. does not affect unit tests. severity: low (unit tests are the primary gate for worktree development).

- **server dep ownership** — `apps/server/pyproject.toml` declares only `attu-logging`; all other server runtime deps (fastapi, httpx, tomlkit, uvicorn, itsdangerous) live in `apps/bot/pyproject.toml`. pre-existing architectural oddity surfaced during phase 0 test-container work. severity: low (uv workspace resolves transitively; no runtime failures). disposition: defer — cleanup-bridge or a standalone dep-ownership pass.

## closed
