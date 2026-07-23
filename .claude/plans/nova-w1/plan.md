# nova-w1: structural prerequisites

workstream 1 of the nova-core modularization. nothing else starts until this is merged to trunk.

## goals

- `doom_bot` package fully renamed to `nova_core`; zero remaining references in `apps/`, `packages/`, `tests/`, `scripts/`; Docker images build under the new name
- `attu_logging` migration complete across all call sites; `nova_core/logging.py` deleted; `attu_logging/webhook.py` imports no bot package; method names corrected site-wide (`warn`→`warning`, `fatal`→`critical`, `trace`/`alert`→`debug`, `send_to_webhook`→`await attu_logging.webhook.send_to_webhook`)
- all 8 bridge bugs fixed; `bot._bot_initialized` flag gates the health endpoint; sample TOML has `[bridge]` section; `__config_version__` bumped to `2.6.0`
- guild config reads `[[guilds]]` array with `role` field; old `[discord.guilds]` primary/secondary format rejected at startup with a clear `ConfigLoadError`
- zero hardcoded attu-specific or doom-named strings in `nova_core/client/`; bot name and welcome message configurable from `[bot]` TOML section

## non-goals

- feature manifest system (workstream 2)
- moving any feature to its own package (workstream 3)
- renaming `attu_models` package - name is tbd per contract; deferred to workstream 3 once content migration is complete
- casino bot scaffold (workstream 4)
- admin repl or fastapi admin endpoints (workstream 5)
- python / npm dependency version bumps (parallel workstream; no ordering constraint)
- mongodb data migrations

## constraints

- each phase must produce a runnable bot; no broken trunk states between phases
- ~422 `doom_bot` import sites in `apps/bot/`, ~1662 in `tests/`; validated by `ruff check`, `basedpyright`, and a grep that covers Dockerfiles, yml, and shell scripts - not just `*.py`
- `attu_logging/webhook.py` imports from `doom_bot` today; that reference bridges to `nova_core` in phase 1 and is fully removed in phase 2; no gap between the two
- `config.bridge` does not exist on `NovaConfig` today; bridge is broken until phase 3; phases 0-2 "runnable" explicitly excludes the bridge
- bridge bug fixes include a test mock gap (`_register_bridge_startup`) that triggers the mock-compensation rule; apply that skill before touching bridge tests in phase 3
- workstreams 2-5 are blocked on trunk merge; pace accordingly

## accepted risks

three risks survived the pre-mortem as residue after mitigation. first: the webhook_url timing split - `attu_logging.configure()` runs at startup before `config.error_hook` is available (on_load stage); the design separates configure() for structlog setup from `set_webhook_url()` called inside `on_load()` after DB connect; if the split is misapplied the error webhook silently posts to None and swallows exceptions. second: after phase 2, `DEBUG=1` no longer lowers the root logger level - `attu_logging/config.py` checks `LOG_LEVEL` not `DEBUG`; developers who relied on `DEBUG=1` for debug output need `LOG_LEVEL=DEBUG` instead; this is a behavioral change with no error and no fallback. third: `SystemConfigDocument.primary_guild` remains in mongodb after phase 4 removes the config attribute that populated it; no data loss, but the field becomes orphaned until workstream 3 cleans it up during feature migration.

### phase 0 - walking skeleton

**status:** closed in 62ba559

**dod:** `python -c "import nova_core; print(nova_core.__version__)"` exits 0 with the expected version string; Dockerfile sed path references `nova_core/__init__.py`; all tool configs (ruff, basedpyright, coverage, pytest) list `nova_core` as a known package; `doom_bot/__init__.py` is unchanged; bot runnable via doom_bot (bridge excluded)

**scope:** create `apps/bot/nova_core/__init__.py` with standalone metadata constants only - copy `__title__`, `__version__`, `__schema__`, `__config_version__`, `__author__`, `__email__`, `__description__`, `__build_time__`, `__license__`, `__copyright__` from `doom_bot/__init__.py`; no imports from doom_bot in this file. update `pyproject.toml`: add `nova_core` to ruff isort `known-first-party`, basedpyright `extraPaths` (apps/bot already present, so nova_core is auto-discovered), `coverage.run.source`. update `apps/bot/Dockerfile`: change all three doom_bot path references to nova_core (the `sed` target in git-info stage, the `COPY` source line, and the stamped `__init__.py` copy). do not touch `doom_bot/__init__.py` or `doom-bot.py`. this retires the "tooling accepts nova_core as a package" unknown without any shim or circular import risk.

**merge gate:** none

### phase 1 - package rename

**status:** pending merge

**dod:** `grep -rn 'doom_bot' apps/ packages/ tests/ scripts/ config/ --include="*.py"` returns zero lines; same grep over Dockerfiles, `*.yml`, `*.sh` returns zero lines; `ruff check` passes; `basedpyright` passes; Dockerfile sed target uses `nova_core/__init__.py`; bot runnable (bridge excluded - `config.bridge` not yet defined)

**scope:** move all source files from `doom_bot/` into `nova_core/` - client/, bridge/, commands/, database/, tasks/, eggs/, wiki/, ccboard/, config.py, signals.py, webhook.py; `logging.py` moves too but is NOT deleted here (phase 2 handles it). update all 422+ `from doom_bot.*` → `from nova_core.*` across `apps/bot/`, `tests/`, `scripts/`. update `attu_logging/webhook.py`: `from doom_bot import config` → `from nova_core import config`; `from doom_bot.client.util import break_at_newline` → `from nova_core.client.util import break_at_newline` - this bridges the package reference so doom_bot can be fully deleted without breaking error reporting. update root `pyproject.toml`: workspace name from `doom-bot` to `nova-core`, isort `known-first-party`, coverage `source`, pytest `pythonpath`. delete `apps/bot/doom_bot/` entirely including the phase 0 nova_core metadata shim. update `apps/bot/Dockerfile`: remove the three doom_bot lines left by the phase 0 additive approach - the two `sed` commands in the git-info stage (`sed -i ... apps/bot/doom_bot/__init__.py`), the `COPY --chown=doom:doom ./apps/bot/doom_bot ...` line in the doombox stage, and the `COPY --from=git-info ... doom_bot/__init__.py ...` stamp line; only nova_core lines should remain after this phase. note: `nova_core/logging.py` exists after this phase and is still imported; phase 2 deletes it.

**merge gate:** phase 0 merged to trunk

### phase 2 - attu_logging migration

**status:** pending merge

**dod:** `grep -rn 'nova_core\.logging\|doom_bot\.logging' . --include="*.py"` returns zero; `nova_core/logging.py` is absent from the filesystem; `attu_logging/webhook.py` contains no bot package imports; `attu_logging.set_webhook_url()` exists and is called from `on_load()` after `config.error_hook` is available; inlined `break_at_newline` in `attu_logging/webhook.py` matches `nova_core/client/util.py` implementation; bot runnable (bridge excluded)

**scope:** `attu_logging/config.py`: add `webhook_url: str | None = None` param to `configure()` and store in module-level `_webhook_url`; add a separate `set_webhook_url(url: str)` function that sets `_webhook_url` independently of the idempotent configure guard - this is the split that handles the startup-vs-on_load timing gap. `attu_logging/webhook.py`: remove all nova_core imports; read URL from `_webhook_url` module store at call time (lazy, not at configure time); inline `break_at_newline`; webhook username placeholder until phase 4 `[bot]` section lands. bot startup (`doom-bot.py`): call `attu_logging.configure(level='DEBUG' if 'DEBUG' in environ else None)` before first logger use - note the `DEBUG` env var must be threaded through here to preserve backward-compat behavior since `attu_logging/config.py` checks `LOG_LEVEL` not `DEBUG` for root logger level. `nova_core/client/events.py` `on_load()`: call `attu_logging.set_webhook_url(config.error_hook)` after DB connect. 46+ call sites: `from nova_core.logging import get_logger` → `import structlog`; `logger = get_logger(__name__)` → `logger = structlog.stdlib.get_logger(__name__)`; fix method names. move `PycordBridgeHandler` class inline to `nova_core/client/__init__.py` (no-op marker; required for test surface). remove `Logger` type alias usages in `util.py`; replace with `structlog.stdlib.BoundLogger` where type annotation is needed. delete `nova_core/logging.py`.

**merge gate:** phase 1 merged to trunk

### phase 3 - bridge bug fixes

**status:** open

**dod:** all 8 bugs from the contract addressed at code level; sample TOML has `[bridge]` section; `__config_version__` in `nova_core/__init__.py` bumped to `2.6.0`; `ruff check` passes; bot runnable with bridge now included (`config.bridge` defined; bridge starts on on_ready)

**scope:** first, read `nova_core/client/events.py` `_do_ready_init()` at line 102 to confirm where `start_bridge_task()` is called and whether its error is swallowed - this determines whether the bridge crash in phases 0-2 was silent or fatal; document the finding in the commit message. then fix all 8 bugs: (1) hmac bypass - add `Field(min_length=1)` to `BridgeConfig.secret` and add `BridgeConfig` model to `nova_core/config.py` with `secret: str = Field(min_length=1)`, `bind_host: str = '127.0.0.1'`, `bot_port: int = 5050`, `replay_window: int = 60`; wire into `NovaConfig.on_init()` from `[bridge]` TOML section; add `[bridge]` section to `config/attu-bot.sample.toml`; bump `__config_version__` to `2.6.0`. (2) startup lockout - in `router.py` `start_bridge_task()`: move `bot._bridge_started = True` to AFTER `await server.serve()` returns; set to `False` on exception. (3) health race - add `bot._bot_initialized: bool = False` on the bot singleton in `nova_core/client/core.py`; set `True` at the end of `_do_ready_init()`; health endpoint reads `bot._bot_initialized` not `bot.is_ready()`. (4) config_version gate - covered by sample toml bump above. (5) avatar_url null - `discord_integration.py` `get_user_info()`: `user.display_avatar.url` unconditionally (remove `if user.avatar else None` guard). (6) `get_guild_roles` silent 200 - match `get_guild_channels` error-handling pattern: `return None` on exception; router endpoint raises 502. (7) `DiscordCache.clear` prefix collision - `k.startswith(prefix + ':')` instead of `k.startswith(prefix)`. (8) `_register_bridge_startup` test mock - apply mock-compensation skill before touching bridge tests; add `_register_bridge_startup` to `_patch_all_startup()` and all inline patch blocks. also address the now-visible `test_bridge_sign.py` pre-existing unit failures (5 tests; unmasked in phase 2; mechanism documented in bugs.md).

**merge gate:** phase 2 merged to trunk

### phase 4 - config restructure and string cleanup

**status:** open

**dod:** sample TOML uses `[[guilds]]` array with `role` field; starting the bot with the old `[discord.guilds]` format raises `ConfigLoadError` with a message that identifies the old key; `grep -rn 'config\.primary_guild\|config\.secondary_server' . --include="*.py"` returns zero; no hardcoded doom/attu strings in `nova_core/client/` or `attu_logging/webhook.py`; `ruff check` passes; bot runnable

**scope:** pre-step: run `grep -rn 'config\.primary_guild\|config\.secondary_server\|primary_guild\b\|NovaConfigRepr' apps/ --include="*.py"` to establish the full call-site list (pre-mortem identified 12+ sites in markers.py, years.py, calendar.py, commands/trees.py, tasks/logo_update.py, config.py, commands/fix.py) before touching any code. then: add `BotConfig` model to `nova_core/config.py` with `name: str` and `welcome_message: str`; wire into `NovaConfig.on_init()` from `[bot]` TOML section; add `[bot]` section to sample TOML with `name = "AttuBot"` and `welcome_message = "welcome to the archipelago {mention}"`. replace `[discord.guilds]` named-key parsing in `NovaConfig.on_init()` with `[[guilds]]` array parsing; build `authorized_guilds` from the list; add role-lookup helper; detect old format (test for `discord.guilds` having `primary` or `secondary` int keys) and raise `ConfigLoadError` with a message naming the old key. remove `config.primary_guild` and `config.secondary_server` attributes; update all confirmed call sites to use `next(g for g in config.guilds.values() if g.role == 'primary')` or the role-lookup helper; update `NovaConfigRepr` TypedDict. `nova_core/client/events.py`: replace hardcoded welcome message with `config.bot.welcome_message.format(mention=member.mention)`; replace `'DoomBot(tm) Premium'` with a neutral string. `attu_logging/webhook.py`: call `attu_logging.set_bot_name(config.bot.name)` at startup alongside `set_webhook_url()`; use the stored name as webhook username instead of placeholder. `tasks/error_hook.py`: `reason=f'{config.bot.name} Error Log'`. `bridge/router.py`: `FastAPI(title='nova bridge', ...)`. while editing config.py, also fix: `if bridge_raw is not None:` (currently `if bridge_raw:`) so an empty `[bridge]` section raises a pydantic validation error rather than silently disabling the bridge (see bugs.md [fix-in-phase-4]). bump `__config_version__` from 2.6.0 (phase 3's new baseline) for the new `[bot]` section and `[[guilds]]` array format. note: `SystemConfigDocument.primary_guild` in attu_models is now orphaned - field remains in mongodb but nothing writes to it from config; this is intentional and tracked for cleanup in workstream 3.

**merge gate:** phase 3 merged to trunk

---

## status

| phase | status |
|---|---|
| 0 - walking skeleton | closed in 56e78e1 |
| 1 - package rename | closed in 3ae889a |
| 2 - attu_logging migration | closed in 17785e5 |
| 3 - bridge bug fixes | pending merge |
| 4 - config restructure and string cleanup | not started |
