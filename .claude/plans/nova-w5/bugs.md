# nova-w5 bugs

## open

- **bridge fix endpoint missing:** `POST /bridge/fix/recalculate-starboard` does not exist in `doom_bot/bridge/router.py`. the `fix.py` admin endpoint ships with a `501` fallback until this lands. tracked here so `bug-triage` can promote it to a real bridge task when phase 3 merges. severity: medium (feature incomplete, not broken). disposition: deferred to nova-w3 or a standalone bridge task.

- **worktree `.secrets/attu-bot.toml` junk directory:** docker creates an empty directory at `.secrets/attu-bot.toml` (owned by root) when the worktree lacks the secrets file. this blocks component and integration tests when running `docker compose` from the worktree. workaround: `sudo rm -rf .secrets && mkdir .secrets && ln -sf /home/jhn/Projects/doom-bot/.secrets/attu-bot.toml .secrets/attu-bot.toml`. does not affect unit tests. severity: low (unit tests are the primary gate for worktree development). disposition: defer; does not block any phase, unit tests unaffected.

- **server dep ownership:** `apps/server/pyproject.toml` declares only `attu-logging`; all other server runtime deps (fastapi, httpx, tomlkit, uvicorn, itsdangerous) live in `apps/bot/pyproject.toml`. pre-existing architectural oddity surfaced during phase 0 test-container work. severity: low (uv workspace resolves transitively; no runtime failures). disposition: defer; cleanup-bridge or a standalone dep-ownership pass.

- **`any(hmac.compare_digest(...))` short-circuits on multiple keys:** current implementation allows early exit when the matching key is not the first in `api_keys`, so timing leaks key list length and partial position. severity: low — typical deployment has one key; threat model does not require multi-key positional secrecy. disposition: defer; revisit in a security hardening pass (not a phase 2/3/4 blocker).

- **`_build_guild_slug_map` misused for slug → guild id resolution in channels/roles:** channels/roles endpoints call `_build_guild_slug_map()` (N bridge calls) just to resolve a slug to a guild id, but the id is already present in `config.guilds`. each additional slug-resolved endpoint added in phase 2+ will repeat this pattern. **blocker: flag before phase 2 adds config endpoints with the same slug resolution.** severity: medium. disposition: fix-in-phase-2; add a direct `config.guilds` slug-to-id lookup helper and use it everywhere the guild id is the only thing needed.

- **`_build_guild_slug_map` stores bridge string id then converts back via `int(guild['id'])`:** `GuildEntry.id` is already an `int`; using `g.id` directly would skip the string round-trip. low severity, no functional impact. disposition: fix-in-phase-2 (bundle with the slug resolution refactor above).

## closed

- **`require_api_key` uses plain string comparison:** fixed in phase 1 (da22118); `hmac.compare_digest` with any-match logic now used in `deps.py`.
