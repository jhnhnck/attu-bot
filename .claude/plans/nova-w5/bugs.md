# nova-w5 bugs

## open

- **bridge fix endpoint missing:** `POST /bridge/fix/recalculate-starboard` does not exist in `doom_bot/bridge/router.py`. the `fix.py` admin endpoint ships with a `501` fallback until this lands. tracked here so `bug-triage` can promote it to a real bridge task when phase 3 merges. severity: medium (feature incomplete, not broken). disposition: deferred to nova-w3 or a standalone bridge task.

- **worktree `.secrets/attu-bot.toml` junk directory:** docker creates an empty directory at `.secrets/attu-bot.toml` (owned by root) when the worktree lacks the secrets file. this blocks component and integration tests when running `docker compose` from the worktree. workaround: `sudo rm -rf .secrets && mkdir .secrets && ln -sf /home/jhn/Projects/doom-bot/.secrets/attu-bot.toml .secrets/attu-bot.toml`. does not affect unit tests. severity: low (unit tests are the primary gate for worktree development). disposition: defer; does not block any phase, unit tests unaffected.

- **server dep ownership:** `apps/server/pyproject.toml` declares only `attu-logging`; all other server runtime deps (fastapi, httpx, tomlkit, uvicorn, itsdangerous) live in `apps/bot/pyproject.toml`. pre-existing architectural oddity surfaced during phase 0 test-container work. severity: low (uv workspace resolves transitively; no runtime failures). disposition: defer; cleanup-bridge or a standalone dep-ownership pass.

- **`any(hmac.compare_digest(...))` short-circuits on multiple keys:** current implementation allows early exit when the matching key is not the first in `api_keys`, so timing leaks key list length and partial position. severity: low — typical deployment has one key; threat model does not require multi-key positional secrecy. disposition: defer; revisit in a security hardening pass (not a phase 2/3/4 blocker).

- **`_CHANNEL_SUFFIXES ('_channel', '_id')` over-matches `guild_id`:** the `_id` suffix causes `PATCH /admin/guilds/{slug}/config/guild_id` (a top-level `GuildConfigDocument` field) to trigger channel slug resolution unnecessarily. works for ints and int-coercible strings but is semantically wrong. location: `config_routes.py` line 22. severity: low. disposition: defer; not a phase 3/4 blocker.

- **`config_routes.py` imports `_build_guild_slug_map` across module boundaries using its private name:** `_build_guild_slug_map` is underscore-prefixed (module-private) in `guilds.py` but imported directly in `config_routes.py`. should be renamed to `build_guild_slug_map` (public) or moved to `slugs.py` where the other slug utilities live. severity: low. disposition: defer; cleanup pass.

## closed

- **`require_api_key` uses plain string comparison:** fixed in phase 1 (da22118); `hmac.compare_digest` with any-match logic now used in `deps.py`.

- **`_build_guild_slug_map` misused for slug → guild id resolution in channels/roles:** resolved in phase 2 (7d797f6); `resolve_guild_id` helper added to `slugs.py` and used in all slug→id lookups. note: `GuildEntry` has no `name` field, so N bridge calls for slug generation are structurally necessary; the original "direct `config.guilds` lookup" scope description was not achievable as written. integration check accepted "no additional bridge calls for guild-id lookup" since `resolve_guild_id` itself makes no bridge calls.

- **`_build_guild_slug_map` stores bridge string id then converts back via `int(guild['id'])`:** resolved in phase 2 (7d797f6); `resolve_guild_id` centralizes the int cast. the `g.id` direct approach was not used since the slug map must be built from bridge response dicts (name required for slugification). functional impact was nil; cast is now in one place.
