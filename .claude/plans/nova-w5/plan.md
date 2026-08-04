# nova-w5 — fastapi admin endpoints + repl client

## goals

1. `/admin/` router on `attu_server` gated on `Authorization: Bearer` against `config.auth.api_keys`
2. guild/channel/role listing endpoints with server-side slug generation (strip non-alphanum, lowercase, spaces→dashes, collision suffix `-2`/`-3`)
3. config get/set endpoints via dot-path key into `GuildConfigDocument`; slug resolution for channel/role fields
4. feature enable/disable endpoints toggling per-guild feature flags in the database
5. reload trigger endpoints (guild/theme/system) proxied to bridge
6. fix endpoints (initial scope: recalculate-starboard) proxied to bridge
7. `scripts/nova_admin.py`: `cmd.Cmd` repl, `httpx` sync client, slug-based name resolution, no snowflakes as arguments

## non-goals

- passkey/webauthn changes
- nova_core package rename (workstream 1 — nova-w1)
- browser web UI for admin operations
- casino bot work (workstream 4 — nova-w4)
- bridge hmac or security model changes

## constraints

- nova-w1 merged to trunk 2026-07-23; TOML shape confirmed: `[auth]` section → `api_keys`; `[[guilds]]` array → `id`, `role` fields. phase 0 stubs carry empty defaults; phase 1 wires `load_config` for both fields.
- python 3.13, uv workspace
- `docker compose run tests` must pass at each phase merge
- no push without explicit instruction
- server calls bridge for all bot operations; the repl never touches the bridge directly
- admin-router test fixtures must build a standalone app directly from the router (not call `create_app()`); `create_app()` has module-level import side effects that break the test container's PYTHONPATH isolation discovered in phase 0.

## accepted risks

the pre-mortem (`pre-mortem.md`) flagged three material risks. `ServerConfig` currently has no `guilds` field — phase 0 adds a `GuildEntry`/`AuthConfig` stub so `GET /admin/guilds` has something to enumerate without waiting for nova-w1. the `recalculate-starboard` fix operation requires a new bridge route that doesn't exist yet; phase 3 ships a `501 Not Implemented` fallback and logs the dependency in `bugs.md` until the bridge side lands. dot-path config key traversal is tested against a real `GuildConfigDocument` fixture (not mock dicts) to catch field-name drift during the nova-w3 feature migration. `cmd.Cmd` session state is factored into a standalone `_AdminSession` dataclass so phase 4 unit tests don't depend on `cmdloop()`.

---

### phase 0 — walking skeleton

**status:** not started

the thinnest end-to-end slice through every layer this workstream will touch: a single `GET /admin/ping` endpoint behind a valid Bearer token.

**scope:**
- `apps/server/attu_server/config.py` — add `GuildEntry(id: int, role: str)` and `AuthConfig(api_keys: list[str] = [])` as optional fields on `ServerConfig` (stubs; nova-w1 owns the full TOML wiring)
- `apps/server/attu_server/deps.py` — add `require_api_key(config: Annotated[ServerConfig, Depends(get_config)], request: Request) -> None` dependency; raises `HTTPException(401)` if `Authorization` header is missing, not a Bearer token, or the key is not in `config.auth.api_keys`
- `apps/server/attu_server/api/admin/__init__.py` — create admin router package; export `router = APIRouter(prefix='/admin', dependencies=[Depends(require_api_key)])`
- `apps/server/attu_server/api/admin/ping.py` — `GET /admin/ping` returning `{"ok": True}`
- `apps/server/attu_server/main.py` — include admin router
- `tests/python/unit/test_admin_ping.py` — three cases: missing header → 401, wrong key → 401, valid key → 200 `{"ok": true}`

**dod:** `GET /admin/ping` returns 200 with a valid key and 401 without; `config.auth` and `config.guilds` fields are present on `ServerConfig` with empty defaults; admin router is included in `main.py`; `ruff check .` clean; `docker compose run tests` passes

**merge gate:** all three auth cases tested; no new mypy/pyright errors in `attu_server`

---

### phase 1 — auth gate + guild listing endpoints

**status:** not started

**scope:**
- `apps/server/attu_server/config.py` — wire `load_config` to populate `config.auth.api_keys` from TOML `[auth].api_keys` and `config.guilds` from TOML `[[guilds]]` array. nova-w1 has shipped the format; gate condition from the 2026-07-23 log note is now satisfied.
- `apps/server/attu_server/deps.py` — replace `key not in config.auth.api_keys` with `not any(hmac.compare_digest(key, k) for k in config.auth.api_keys)` for timing-safe comparison (bug tracked in bugs.md; natural home before guild endpoints ship).
- `apps/server/attu_server/api/admin/slugs.py` — `slugify(name: str) -> str` (strip non-alphanumeric except spaces/dashes, lowercase, spaces→dashes, collapse consecutive dashes); `make_slug_map(items: list[dict]) -> dict[str, dict]` (builds `{slug: item}` with `-2`/`-3` collision suffixes)
- `apps/server/attu_server/api/admin/guilds.py` — three endpoints:
  - `GET /admin/guilds` — iterates `config.guilds`; calls `bridge.get_guild_info(guild_id)` for each; returns `[{id, name, slug, role}]`
  - `GET /admin/guilds/{slug}/channels` — resolves slug → guild id; calls `bridge.get_guild_channels(guild_id)`; returns `[{id, name, slug, type}]`
  - `GET /admin/guilds/{slug}/roles` — resolves slug → guild id; calls `bridge.get_guild_roles(guild_id)`; returns `[{id, name, slug}]`
- `tests/python/unit/test_admin_guilds.py` — slug generation correctness (including collision cases), listing endpoints with mocked `BridgeClient`, 404 on unknown guild slug; load_config round-trip for `[auth]` and `[[guilds]]` sections

**slug generation rules:**
- strip characters that are neither alphanumeric, space, nor dash
- lowercase
- spaces → dashes
- collapse consecutive dashes to one
- collision: first occurrence keeps the base slug; second gets `-2`, third gets `-3`
- slug generation is deterministic per call — order of items in the list determines who wins collisions

**dod:** `load_config` wires `config.auth.api_keys` from `[auth]` TOML section and `config.guilds` from `[[guilds]]` array; timing-safe key comparison in `require_api_key`; three listing endpoints return slugged data; `GET /admin/guilds` calls bridge once per guild in `config.guilds`; slug uniqueness and collision tests pass; 404 on unknown slug; `ruff check .` clean; `docker compose run tests` passes

**merge gate:** slug collision test covers at least two items with the same normalized name; bridge mock asserts call count matches `len(config.guilds)`; load_config test uses a minimal TOML string with `[auth]` and one `[[guilds]]` entry

---

### phase 2 — config get/set endpoints

**status:** not started

**scope:**
- `apps/server/attu_server/api/admin/config_routes.py` — two endpoints (file named `config_routes.py` to avoid shadowing stdlib `config`):
  - `GET /admin/guilds/{slug}/config/{key}` — loads `GuildConfigDocument` from db; traverses dot-path key; returns `{"key": "...", "value": ...}`
  - `PATCH /admin/guilds/{slug}/config/{key}` — body: `{"value": ...}`; loads document; resolves slug to snowflake if the terminal field is a channel or role id; sets field at key path; validates with pydantic; saves; triggers `bridge.invalidate_guild_cache()` + `bridge.trigger_reload('guild', guild_id)`
- `tests/python/unit/test_admin_config.py` — uses a real `GuildConfigDocument` fixture (not mock dicts); tests: get roundtrip, set roundtrip, slug-to-snowflake resolution for channel fields, 422 on invalid key path, 422 on type mismatch, 404 on unknown guild slug

**dot-path key contract:**
- key format: `<top-level-field>.<nested-field>` (e.g. `starboard.channel`, `ccboard.threshold`)
- traversal: split on `.`; walk the document model using `model_fields` at each level; raise 422 if a segment doesn't match any field name
- set path: reconstruct the nested update using model `model_validate`; don't mutate dicts directly
- channel/role field detection: if the terminal field name ends with `_id` or `_channel` or `_role`, attempt slug resolution against the cached guild channel/role list before writing; fall back to raw int if no slug match

**dod:** config round-trip tested against a real `GuildConfigDocument` fixture; slug-to-snowflake resolution works for channel fields; invalid key path returns 422; unknown guild returns 404; bridge cache invalidate and reload called on every successful set; `docker compose run tests` passes

**merge gate:** dot-path traversal test uses a `GuildConfigDocument` instance with real field names (not a plain dict); no `getattr(obj, key)` without `hasattr` guard

---

### phase 3 — feature/reload/fix endpoints

**status:** not started

**scope:**
- `apps/server/attu_server/api/admin/features.py`:
  - `POST /admin/guilds/{slug}/features/{feature}/enable` — loads `GuildConfigDocument`; sets `features[feature]['enabled'] = True` (creates sub-doc with defaults if missing); saves; triggers guild cache invalidate + reload via bridge
  - `POST /admin/guilds/{slug}/features/{feature}/disable` — same but `enabled = False`
- `apps/server/attu_server/api/admin/reload.py`:
  - `POST /admin/reload/guild` — body: `{"guild_slug": "attu"}`; resolves slug → id; calls `bridge.trigger_reload('guild', guild_id)`
  - `POST /admin/reload/theme` — calls `bridge.trigger_reload('theme')`
  - `POST /admin/reload/system` — calls `bridge.trigger_reload('system')`
- `apps/server/attu_server/api/admin/fix.py`:
  - `POST /admin/guilds/{slug}/fix/recalculate-starboard` — calls bridge `POST /bridge/fix/recalculate-starboard`; if bridge returns 404 (endpoint not yet implemented), returns `501 Not Implemented` with body `{"detail": "bridge fix endpoint not yet available", "operation": "recalculate-starboard"}`
- `tests/python/unit/test_admin_features.py`, `test_admin_reload.py`, `test_admin_fix.py`

**bridge fix endpoint dependency:**
`POST /bridge/fix/recalculate-starboard` does not yet exist in `doom_bot/bridge/router.py`. this is tracked in `bugs.md`. phase 3 ships the `fix.py` server-side endpoint with a `501` fallback; the bridge side is a separate task (nova-w3 or standalone). the `501` path must be tested — do not treat it as dead code.

**dod:** feature toggle enable/disable persist to db and trigger guild reload; reload endpoints proxy correctly to bridge with right signal types; fix endpoint returns 200 when bridge responds 200, 501 when bridge returns 404; `501` path covered by a test; `docker compose run tests` passes

**merge gate:** feature enable/disable test verifies the db write (mock storage) and the bridge trigger call separately; fix `501` test present and passing

---

### phase 4 — repl client

**status:** not started

**scope:**
- `scripts/nova_admin.py` — `cmd.Cmd`-based repl; session state in a standalone `_AdminSession` dataclass

**session state (`_AdminSession`):**
```python
@dataclass
class _AdminSession:
    api_key: str
    server_url: str
    current_guild: dict | None = None  # {id, name, slug, role}
    channels: list[dict] = field(default_factory=list)  # [{id, name, slug, type}]
    roles: list[dict] = field(default_factory=list)  # [{id, name, slug}]
```

**commands:**
```
nova-admin> guilds                          # list all: slug | name
nova-admin> use <guild-slug>                # set current_guild; fetch+cache channels/roles
nova-admin> channels                        # list cached: slug | name | type
nova-admin> roles                           # list cached: slug | name
nova-admin> config get <key>
nova-admin> config set <key> <value>
nova-admin> feature enable <name>
nova-admin> feature disable <name>
nova-admin> reload guild
nova-admin> reload theme
nova-admin> fix recalculate-starboard
nova-admin> refresh                         # re-fetch channels/roles for current guild
nova-admin> exit
```

**startup:**
- `--api-key` flag or `$ATTU_ADMIN_KEY` env var; exits with a clear error message if neither is set
- `--server` flag or `$ATTU_SERVER_URL` env var; default `http://localhost:8000`
- uses `httpx.Client` (sync) for all requests; wraps every call with a uniform error handler that prints status + `detail` field and returns `None` on non-2xx

**testability boundary:**
- `_AdminSession` dataclass is the only thing unit tests touch; test slug resolution, cache invalidation logic, and the `use` / `refresh` state transitions against it
- `do_*` dispatch methods in the `Cmd` subclass are thin: parse args, call a session method, print result; not independently tested
- `tests/python/unit/test_nova_admin.py` covers: `_AdminSession` state transitions, slug lookup in cached channel/role lists, `use` with unknown slug error path, `refresh` updating session state

**dod:** all listed commands work against a running dev server (manual smoke test documented in `log.md`); `_AdminSession` unit tests cover state transitions and slug resolution; unknown slug and missing guild-selection error paths tested; `ruff check scripts/nova_admin.py` clean; `docker compose run tests` passes

**merge gate:** manual smoke test record in `log.md` showing `guilds`, `use`, `config get`, `config set`, `feature enable`, `reload guild` completing without error against dev server

---

## status

| phase | status |
|---|---|
| 0 — walking skeleton | closed in 0c31d46 |
| 1 — auth gate + guild listing | not started |
| 2 — config get/set | not started |
| 3 — feature/reload/fix | not started |
| 4 — repl client | not started |
