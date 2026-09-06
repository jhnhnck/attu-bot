# bug log

reported bugs live here, separate from the feature backlog in `docs/to-do.md`. the `to-do` skill owns the format and the triage rules: severity (`blocker` / `important` / `nit`) and disposition (`fix-now` / `fix-in-phase-N` / `defer` / `won't-fix`). triage classifies; it never fixes code itself.

format and conventions match `docs/to-do.md` (all lowercase, `- ⭕` for open / `- 🔴` for resolved). see the [meta](#meta) section for the format reference.

---

## untriaged

### testing

- ⭕ `bug` `tests/python/integration/test_startup.py` `TestBotReadyPath` fails in all environments: main checkout fails with `ConfigLoadError: config file version 2.6.0 is below required 2.7.0` (dev secrets out of date) and with `missing config file` (path lookup issue); worktrees fail because no secrets are mounted. found during item/tests-no-env-secrets; pre-existing before that slice. carried from plan: nova-w2 (2026-08-09)
- ⭕ `bug` `docker-compose.dev.yml` `tests` service has had no `.secrets` mount and no `ATTU_CONFIG_FILE` since `36f6fee` (2026-08-02), so integration tests run through `docker compose run --build --rm tests` cannot find a config file; `TEST_DB_URL` covers unit/component only. fix: mount `.secrets` read-only into that one service, or accept that integration tests are venv-only (README already documents docker as unit/component-only). carried from plan: venv-tests (2026-09-03)


### starboard

- ⭕ `bug` starboard doesn't render multiple images from messages with more than one attachment (from cowboy)
- ⭕ `bug` stickers and voice memos still have rendering issues; voice memos don't show the no-preview text either; gif links include a png instead of the gif/gifv

### wiki

- ⭕ `bug` `commands/wiki.py` wiki lookup pagination allows negative index via rapid button clicks — `_prev_callback`/`_next_callback` have no bounds check; the `disabled` state only rebuilds after the async wiki fetch, so concurrent clicks bypass it; corrupted index persists to db (from banarnar)

### scheduling

- ⭕ `bug` `commands/time.py:34` `time_advance` passes `cfg.guild.id` to `scheduler.add_job` but `GuildConfig` has no `.guild` attr; should be `cfg.id`

### architecture

- ⭕ `smell` `packages/shared-models/attu_models/repositories.py:36` `attu_models` imports `nova_core.config.{BotTheme, GuildConfig}` inside a `TYPE_CHECKING` block; the runtime cycle is broken but the type-hint coupling means shared-models still knows about `nova_core.config`. fix would either move `BotTheme` / `GuildConfig` into shared-models or generalize the repository signatures to accept protocols (from structlog phase 1 retro; import updated to nova_core in nova-w1 phase 1)

### admin / attu_server

- ⭕ `bug` `apps/server/attu_server/api/admin/config_routes.py` `get_guild_config` and `patch_guild_config` return channel and role snowflakes as JSON integers (`{'key': key, 'value': resolved}` after `_resolve_snowflake` coerces to `int`); the CLAUDE.md snowflake-precision pitfall says ids must cross into JSON as strings. harmless for `scripts/nova_admin.py` (python), wrong for any JS consumer. fix: stringify int values for keys ending in `_channel` / `_id` on the way out, or return them as strings throughout the admin api. found 2026-09-03 during the feature-completion skill refresh
- ⭕ `nit` `apps/server/attu_server/deps.py` `any(hmac.compare_digest(...))` short-circuits on multi-key `api_keys` lists — timing leaks key position; low risk for single-key deployments (typical); timing-safe fix would compare all keys unconditionally. carried from plan: nova-w5 (2026-08-12)
- ⭕ `nit` `apps/server/attu_server/api/admin/config_routes.py:22` `_CHANNEL_SUFFIXES = ('_channel', '_id')` over-matches `guild_id` (top-level `GuildConfigDocument` field), triggering channel slug resolution for `guild_id` patches unnecessarily; works for ints and int-coercible strings but is semantically wrong. carried from plan: nova-w5 (2026-08-12)
- ⭕ `nit` `apps/server/attu_server/api/admin/config_routes.py` imports private `_build_guild_slug_map` across module boundary from `guilds.py`; should be made public (`build_guild_slug_map`) or moved to `slugs.py` alongside other slug utilities. carried from plan: nova-w5 (2026-08-12)
- ⭕ `nit` `scripts/nova_admin.py` `AdminCmd.do_config/do_feature/do_reload/do_fix` call `self.session._request()` directly, bypassing the session-method layer; these `do_*` paths have no unit test coverage. low severity — functional behaviour correct. carried from plan: nova-w5 (2026-08-12)
- ⭕ `nit` `tests/python/unit/test_nova_admin.py` `test_select_guild_channels_error_returns_false` asserts `current_guild is None` but does not assert the roles endpoint was not called when channels fail. minor coverage gap. carried from plan: nova-w5 (2026-08-12)

### nova-core / bridge

- ⭕ `bug` `nova_core/client/markers.py` `YearMarker.mark()` — `channel` parameter defaults to the primary guild's id (a snowflake) when not provided, but `channel` is supposed to be a channel id; pre-existing logic bug preserved during nova-w1 phase 4 migration; fix requires auditing all callers of `mark()` to determine the intended default. carried from plan: nova-w1 (2026-07-23)
- ⭕ `nit` `nova_core/bridge/router.py:149-167` — `bot._bridge_started` is only True after `server.serve()` exits (not while running); the duplicate-start guard at line 149 is therefore always False during normal operation; functionally safe because `on_ready.has_run` prevents re-entry; clean fix: set True at task-creation time, clear to False only on exception. carried from plan: nova-w1 (2026-07-23)
- ⭕ `nit` `nova_core/bridge/hmac.py:47` — lazy `from fastapi import HTTPException` inside `verify()` is redundant now that fastapi is a declared dep; the module-level import via `contextlib.suppress` already covers it. carried from plan: nova-w1 (2026-07-23)
- ⭕ `nit` `nova_core/bridge/hmac.py:13` — comment "fastapi is absent in unit/component test containers" is stale; fastapi is now a declared dep; real reason for the module-level import is that FastAPI calls `get_type_hints(verify)` at route-registration time and needs `Request` resolvable in globals. carried from plan: nova-w1 (2026-07-23)

### testing

- ⭕ `bug` bridge startup wiring (`start_bridge_task()` called from `_do_ready_init()` after the `test_mode` guard) has zero integration test coverage; all integration tests use `test_mode=True` which returns before the bridge block; compensating test needs `test_mode=False` + mock uvicorn; apply mock-compensation skill. carried from plan: nova-w1 (2026-07-23)
- ⭕ `nit` `tests/python/unit/test_start_bot_loop.py` and `tests/python/integration/test_startup.py` — use `patch.object(nova_core.bot, ...)` and `isinstance(nova_core.bot, ...)` patterns; `nova_core/__init__.py` does not re-export `bot`; correct path is `nova_core.client.core.bot`; these are pre-existing failures in the unit/integration baseline (not component tests). carried from plan: nova-w1 phase 1 (2026-07-23)
- ⭕ `nit` `tests/python/unit/test_start_bot_loop.py::TestSetupDiscordLogging::test_sets_discord_http_logger_to_debug` — asserts `discord.http` level is unconditionally `DEBUG` but `_setup_discord_logging()` has been conditional (`DEBUG in environ`) since at least d16d1b2; `TestDiscordHttpLevelGating` in `test_logging.py` covers both branches correctly; fix is to delete the stale test. carried from plan: nova-w1 phase 2 (2026-07-23)
- ⭕ `nit` vestigial `mock_logger.send_to_webhook = AsyncMock()` in `test_task_error_hook.py`, `test_task_logo_update.py`, `test_scheduler.py`, `test_task_presence.py` — method no longer exists on `structlog.stdlib.BoundLogger`; no assertion checks the attribute; delete or replace with `patch('attu_logging.webhook.send_to_webhook', ...)`. carried from plan: nova-w1 phase 2 (2026-07-23)

### linting

- ⭕ `nit` `scripts/coverage_report.py:52,54,111,171` four pre-existing ruff errors (PTH120, PLC0206, PTH123 x2) — `os.path.dirname` and `open()` calls that should use `Path`; auto-fixable with `ruff check --fix scripts/coverage_report.py` (spotted during drop-legacy-web slice)
- ⭕ `nit` `.claude/plans/structlog/plan.md` pre-existing `ruff format --check` violation (trailing whitespace or line-length in the markdown file); ruff flags it in the workspace check; auto-fixable with `ruff format .claude/plans/structlog/plan.md` (spotted during drop-legacy-web slice)

### upstream / dependencies

- ⭕ `bug` `discord/client.py:250` pycord `DeprecationWarning` on python 3.13 — `asyncio.get_event_loop()` called without a running loop; will break on a future python version; may need a pycord upgrade or workaround

### deploy

- ⭕ `bug` `.env` sets `ATTU_CONFIG_FILE=./assets/attu-bot.toml`, a path that does not exist anywhere in the repo (README documents `.secrets/attu-bot.toml`); nothing in compose currently reads it (the `tests` service has no `env_file:`), so it is inert today but wrong for anything else that sources `.env`. carried from plan: venv-tests (2026-09-03)

---

## triaged

_(empty; populated at triage)_

---

## resolved

- 🔴 `2026-07-20` `apps/chat/attu_chat/web/routes.py` broken imports from deleted `doom_bot.web` modules — resolved by deleting `apps/chat/` entirely in e4920c4d (drop-chat slice)
- 🔴 `2026-08-05` `tests/python/unit/test_feature_loader.py:10` `TZ=UTC`/`_time.tzset()` boilerplate — removed in 84033bf (nova-w2 phase 1)
- 🔴 `2026-09-06` `config/attu-bot.sample.toml` `[features].enabled` example listed `"trees"` and `"reminders"` as bare names; `loader.load_all` calls `importlib.import_module`, so both logged "feature not found, skipping" and silently never loaded. corrected to `nova_core.trees` / `nova_core.reminders`; any deployed config copied from the sample needs the same fix
- 🔴 `2026-09-06` `scripts/deploy.py` hardcoded `_epoch_toml` out of sync with `~/.attu-epoch.toml`; migrated `compute_attu_year()` to read the file directly

---

## meta

### format

untriaged: `- ⭕ \`bug\` [optional file:line] description (optional source/reporter)`

triaged: `- [<severity>] <title> → <disposition> · <note>`; group by severity under the `## triaged` heading

resolved: `- 🔴 \`<date>\` description`; sort chronologically (oldest first), prune entries no longer referenced

### severity (highest to lowest)

- `blocker` — ship is unsafe with this present (data loss, security, broken core flow, regression of a shipped feature)
- `important` — correctness gap or real annoyance; workaround exists or impact is bounded
- `nit` — polish, minor inconsistency, low-value cleanup

severity is about impact, not effort.

### disposition

- `fix-now` — interrupt current work; rare, only true blockers found mid-phase
- `fix-in-phase-N` — schedule into a specific upcoming phase; name the phase
- `defer` — keep in the log; revisit at next triage or before ship
- `won't-fix` — explicitly close, with a one-line reason (mandatory)

defaults: blockers → fix-now or fix-in-phase-N (never defer); important → fix-in-phase-N or defer; nits → defer or won't-fix.

### triage workflow

triage per the `to-do` skill when:

- the untriaged list grows after a phase wraps
- before a ship verdict
- the user asks to "triage", "go through the bugs", "what's blocking ship", etc.

read every entry in full, assign severity + disposition, and surface patterns when 3+ items cluster around the same area, premise, or root cause. cluster patterns are a plan-shape signal and feed the plan-revision step of `phase-close`.

### sections

- **untriaged** — open bugs awaiting triage
- **triaged** — open bugs with a severity + disposition assigned
- **resolved** — fixed bugs kept for reference; pruned when no longer relevant
- **meta** — this section; describes the doc format and triage workflow

### metadata

```yaml
last_updated: 2026-08-22
total_resolved: 2
```

## open

- **mkdocstrings cannot import attu_logging** — packages/attu-logging/pyproject.toml has `package = false`, so uv does not install attu_logging into the venv; mkdocstrings raises ModuleNotFoundError when the api reference page is added; phase 1 will need to either set `package = true` for attu-logging or configure a PYTHONPATH workaround before the api reference build can succeed
