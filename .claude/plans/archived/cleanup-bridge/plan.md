# cleanup-bridge

## context

eight bridge correctness bugs confirmed by multi-agent code review: hmac auth bypass (empty secret accepted), permanent startup lockout on uvicorn crash, health-check race (`bot.is_ready()` before `init_database()`), `__config_version__` hard gate with sample toml still at `2.5.4` and no `[bridge]` section, `avatar_url` null for ~40% of users, `get_guild_roles` silent http 200 on error, `DiscordCache.clear` prefix collision, `_register_bridge_startup()` missing from test mock.

structural debt: `doom_bot/logging.py` and `packages/attu-logging/attu_logging/config.py` are near-duplicate implementations that have already drifted; `attu_logging/webhook.py` lazily imports `doom_bot.config` and `doom_bot.client.util.break_at_newline`, silently failing outside the bot process. the wiki client imports `doom_bot.client.core.config` at module level and `doom_bot.__email__/__title__/__version__` in `client.py`.

dependabot: `aiohttp` (direct dep) has 7 cves; npm dev deps (`vite`, `undici`, `brace-expansion`) have multiple high/moderate alerts; codeql flagged url sanitization in test files.

## goals

- all 8 bridge bugs fixed; `config/attu-bot.sample.toml` updated to `2.6.0` with `[bridge]` section
- `doom_bot/logging.py` deleted; all 46 call sites migrated to `attu_logging`
- `attu_logging/webhook.py` has zero `doom_bot` imports; `webhook_url` set once via `configure()`
- wiki client lives in `packages/attu-wiki/` with zero `doom_bot` imports
- `aiohttp` and npm dev deps bumped; codeql alerts investigated

## non-goals

- chat app revival
- web redesign phases
- general compartmentalization beyond wiki extraction
- porting `attubotlogger` or custom levels to `attu_logging` — use attu_logging as-is

## constraints

- python 3.13, uv workspace
- `docker compose run tests` must pass at each phase merge
- no push without explicit instruction
- dev branch only

---

## phases

### phase 0 — bridge bug fixes

**files:**
- `apps/bot/doom_bot/bridge/router.py`
- `apps/bot/doom_bot/bridge/discord_integration.py`
- `apps/bot/doom_bot/config.py`
- `apps/bot/doom_bot/client/__init__.py`
- `tests/python/unit/test_start_bot_loop.py`
- `config/attu-bot.sample.toml`

**fixes:**
1. `_bridge_started` lockout — set flag only after `_serve()` completes successfully; clear on crash; use a running-task reference to guard re-entry on rapid reconnects
2. hmac bypass — `secret: str = Field(min_length=1)` on `BridgeConfig`
3. health race — add `bot._bot_initialized` flag set at end of `_do_ready_init()`; health endpoint returns `bot_ready: getattr(bot, '_bot_initialized', False)`
4. sample toml — bump `config_version` to `2.6.0`; add `[bridge]` section with placeholder values
5. `avatar_url` — use `user.display_avatar.url` unconditionally
6. `get_guild_roles` — return `None` on exception; router raises 502 matching `get_guild_channels`
7. `DiscordCache.clear` — append `':'` to prefix before `startswith` comparison
8. test mock — add `doom_bot.client._register_bridge_startup` to `_patch_all_startup()` and all inline patch blocks in `TestStartBotLoopPipeline`

**dod:** all 8 bugs fixed; sample toml updated; `ruff check .` clean; `docker compose run tests` passes

---

### phase 1 — migrate bot to attu_logging; delete doom_bot/logging.py

**extend `attu_logging`:**
- `attu_logging/config.py` — add `webhook_url: str | None = None` parameter to `configure()`; store module-level
- `attu_logging/webhook.py` — read `webhook_url` from module-level store; remove lazy `doom_bot` imports; inline `break_at_newline` logic (last newline before char limit)

**bot startup:**
- pass `webhook_url=config.error_hook` into `attu_logging.configure()` call at startup (in `doom-bot.py` or `client/__init__.py`)

**migrate 46 call sites (mechanical, one line each for most):**
- `from doom_bot.logging import get_logger` → `import structlog` + `logger = structlog.stdlib.get_logger(__name__)`
- `logger.warn(...)` → `logger.warning(...)`
- `logger.fatal(...)` → `logger.critical(...)`
- `logger.trace(...)` / `logger.alert(...)` → `logger.debug(...)`
- `logger.send_to_webhook(err)` → `await attu_logging.webhook.send_to_webhook(err)`
- `Logger` type alias usages (`client/util.py`) → `structlog.stdlib.BoundLogger`

**delete:**
- `apps/bot/doom_bot/logging.py`

**tests:**
- `tests/python/unit/test_logging.py` — rewrite against `attu_logging` public api; remove tests for `AttubotLogger` internals that no longer exist

**dod:** `doom_bot/logging.py` does not exist; `attu_logging/webhook.py` has zero `doom_bot` imports; all 46 production files import from `attu_logging` or `structlog` directly; `ruff check .` clean; tests pass

---

### phase 2 — extract wiki to packages/attu-wiki/

**walking skeleton probe first:** create `packages/attu-wiki/pyproject.toml` + empty `attu_wiki/__init__.py`; add to workspace root and `apps/bot/pyproject.toml`; verify `uv sync` succeeds before moving any code.

**new package (`packages/attu-wiki/attu_wiki/`):**
- move `auth.py`, `pages.py`, `search.py`, `admin.py`, `models.py`, `client.py` from `apps/bot/doom_bot/wiki/`
- `client.py`: add `user_agent: str` to `WikiClient.__init__`; remove `from doom_bot import __email__, __title__, __version__`
- all modules: replace logging import with `import structlog; logger = structlog.stdlib.get_logger(__name__)`
- `packages/attu-wiki/pyproject.toml`: deps `httpx`, `structlog`, `pydantic`

**bot shim (`apps/bot/doom_bot/wiki/__init__.py`):**
- import `WikiClient` and models from `attu_wiki`
- `get_wiki()` singleton: constructs user-agent from `doom_bot.__title__/__version__/__email__`; passes `endpoint=config.wiki.endpoint`, `user_agent=...` to `WikiClient`
- retain `setup(bot)`

**workspace wiring:**
- `apps/bot/pyproject.toml` — add `attu-wiki`
- root `pyproject.toml` — add `packages/attu-wiki` to `[tool.uv.workspace]`

**tests:**
- `test_wiki_http.py`, `test_wiki_client.py`, `test_commands_wiki.py` — update imports to `attu_wiki`

**dod:** `packages/attu-wiki/` exists with all modules; zero `doom_bot` imports in `attu_wiki/`; `doom_bot/wiki/__init__.py` under 30 lines; `ruff check packages/attu-wiki/` clean; tests pass

---

### phase 3 — dependency updates

**python (pip):**
- bump `aiohttp` to latest in `apps/bot/pyproject.toml`; `uv lock --upgrade-package aiohttp`
- `urllib3` will likely resolve transitively
- `msgpack`, `idna`, `pip` alerts are transitive/build-tool — not ours to fix directly; document rationale

**npm:**
- `pnpm update vite undici brace-expansion` in the js workspace
- verify `npm run lint` still passes

**codeql:**
- investigate 6 "incomplete url substring sanitization" alerts in `tests/python/unit/test_eggs.py` (lines 142, 246, 480, 530, 834, 879) and `test_commands_wiki.py` (line 108)
- almost certainly false positives in test code; dismiss with rationale or fix if real

**dod:** `aiohttp` bumped; npm dev deps bumped; codeql alerts investigated and either dismissed with documented rationale or fixed; tests pass

---

## status

| phase | status |
|---|---|
| 0 — bridge bug fixes | not started |
| 1 — migrate to attu_logging; delete doom_bot/logging.py | not started |
| 2 — extract wiki to packages/attu-wiki/ | not started |
| 3 — dependency updates | not started |
