# bug log

reported bugs live here, separate from the feature backlog in `notes/to-do.md`. run the `bug-triage` skill (`~/.claude/skills/bug-triage/`) to assign severity (`blocker` / `important` / `nit`) and disposition (`fix-now` / `fix-in-phase-N` / `defer` / `won't-fix`) — the skill is the cut-line authority and does not fix code itself.

format and conventions match `notes/to-do.md` (all lowercase, `- ⭕` for open / `- 🔴` for resolved). see the [meta](#meta) section for the format reference.

---

## untriaged

### testing

- ⭕ `bug` `tests/python/integration/test_startup.py` `TestBotReadyPath` fails in all environments: main checkout fails with `ConfigLoadError: config file version 2.6.0 is below required 2.7.0` (dev secrets out of date) and with `missing config file` (path lookup issue); worktrees fail because no secrets are mounted. found during item/tests-no-env-secrets; pre-existing before that slice.


### starboard

- ⭕ `bug` starboard doesn't render multiple images from messages with more than one attachment (from cowboy)
- ⭕ `bug` stickers and voice memos still have rendering issues; voice memos don't show the no-preview text either; gif links include a png instead of the gif/gifv

### wiki

- ⭕ `bug` `commands/wiki.py` wiki lookup pagination allows negative index via rapid button clicks — `_prev_callback`/`_next_callback` have no bounds check; the `disabled` state only rebuilds after the async wiki fetch, so concurrent clicks bypass it; corrupted index persists to db (from banarnar)

### scheduling

- ⭕ `bug` `commands/time.py:34` `time_advance` passes `cfg.guild.id` to `scheduler.add_job` but `GuildConfig` has no `.guild` attr; should be `cfg.id`

### architecture

- ⭕ `smell` `packages/shared-models/attu_models/repositories.py:36` `attu_models` imports `nova_core.config.{BotTheme, GuildConfig}` inside a `TYPE_CHECKING` block; the runtime cycle is broken but the type-hint coupling means shared-models still knows about `nova_core.config`. fix would either move `BotTheme` / `GuildConfig` into shared-models or generalize the repository signatures to accept protocols (from structlog phase 1 retro; import updated to nova_core in nova-w1 phase 1)

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

- ⭕ `smell` `scripts/deploy.py:37-44` the attu-year epoch snapshot (`_epoch_toml`) is hardcoded inline and manually re-pasted from `/fix epoch` whenever it changes. tree-editor's `publish-package.zsh` (attu-standalone-packaging plan) now reads the same epoch from a shared `~/.attu-epoch.toml` file on the host instead of duplicating the snapshot a third time. `deploy.py` should migrate `compute_attu_year()` to read that same file instead of `_epoch_toml`, so there's one canonical epoch copy on the host, not two independently-updated ones (from cross-repo work in tree-editor, not yet actioned here)

---

## triaged

_(empty — populate via the `bug-triage` skill)_

---

## resolved

- 🔴 `2026-07-20` `apps/chat/attu_chat/web/routes.py` broken imports from deleted `doom_bot.web` modules — resolved by deleting `apps/chat/` entirely in e4920c4d (drop-chat slice)

---

## meta

### format

untriaged: `- ⭕ \`bug\` [optional file:line] description (optional source/reporter)`

triaged: `- [<severity>] <title> → <disposition> · <note>` per the `bug-triage` skill emit format; group by severity under the `## triaged` heading

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

invoke the `bug-triage` skill when:

- the untriaged list grows after a phase wraps
- before `ship-readiness` is run
- the user asks to "triage", "go through the bugs", "what's blocking ship", etc.

the skill reads every entry in full, assigns severity + disposition, and surfaces patterns when 3+ items cluster around the same area, premise, or root cause. cluster patterns get handed to `plan-revise` for phase-level rework.

### sections

- **untriaged** — open bugs awaiting triage
- **triaged** — open bugs with a severity + disposition assigned
- **resolved** — fixed bugs kept for reference; pruned when no longer relevant
- **meta** — this section; describes the doc format and triage workflow

### metadata

```yaml
last_updated: 20 July 2026
total_resolved: 1
```
