# structlog — finish the migration

## context

commit `4d998910 refactor(logging): structlog under the legacy get_logger; observability sweep + JSON option` added structlog under a 246-line wrapper (`apps/bot/doom_bot/logging.py`) that preserved every legacy call-site shape. the original brief asked for the import-path preservation explicitly. it was the wrong call: the wrapper grew to ~3× the size of the logger it replaced, the workspace cycle the migration was *meant* to break is still hidden under an "ambient import" comment in `packages/shared-models/pyproject.toml`, and 75% of call sites still pass f-strings into a single `event` slot.

this plan tears down the wrapper and finishes the migration the right way: every project module imports `structlog` directly, configure runs once at each app entrypoint, and `shared-models` carries no project-local logger dependency.

a separate, recently-shipped fix (`apps/bot/doom_bot/client/__init__.py:_setup_discord_logging`) preserves the discord.http DEBUG-vs-WARNING gate. the new configure must keep that semantics in place; it is not in scope to re-litigate.

---

## goals

each goal is a co-equal, grep-checkable end state. none of them is "the goal" — the migration ships when all five hold.

1. **shared-models has zero `doom_bot.logging` imports.**
   check: `grep -rE 'from doom_bot.logging|import doom_bot.logging' packages/` returns 0 lines.

2. **no project-local logger wrapper class.**
   check: `apps/bot/doom_bot/logging.py` does not exist; `git grep -E 'class AttubotLogger|PycordBridgeHandler'` returns 0 lines.

3. **call sites use `structlog.stdlib.get_logger(__name__)` directly.**
   check: `git grep -E 'from doom_bot.logging import get_logger'` returns 0 lines.

4. **`send_to_webhook` is a free function, not a logger method.**
   check: `git grep 'logger.send_to_webhook'` returns 0 lines.

5. **single configure-at-entrypoint per process.**
   check: each of `apps/bot/doom-bot.py`, `apps/chat/attu-chat.py`, and the `apps/server/` entry calls `attu_logging.configure()` exactly once at startup; no module-level `_configure()` runs at import time.

soft goals (not blocking ship): convert f-strings to structured kwargs where the structure is obvious; tighten level pins for any newly-discovered noisy library logger.

---

## architecture

### where the new code lives

```
packages/attu-logging/
  pyproject.toml                  # deps: structlog
  attu_logging/
    __init__.py                   # exports `configure`, `webhook`
    config.py                     # configure(); foreign_pre_chain bucket resolver;
                                  # _MaxLevelFilter; library-noise pinning
    webhook.py                    # send_to_webhook(error, location='', logger_name='')
                                  # — free function; no logger.send_to_webhook anywhere
```

`attu-logging` is a workspace member; `apps/bot`, `apps/chat`, `apps/server`, and `packages/shared-models` all add it as a dep. it depends only on `structlog`, breaking the cycle.

### entrypoint shape

```python
# apps/bot/doom-bot.py — first lines
from attu_logging import configure
configure()

# everything else after this point can safely create module-level loggers
```

```python
# packages/shared-models/attu_models/connection.py
import structlog
logger = structlog.stdlib.get_logger(__name__)
```

```python
# packages/shared-models/attu_models/repositories.py — webhook usage
from attu_logging.webhook import send_to_webhook
await send_to_webhook(err, location='reconcile')
```

### what configure() does

(same surface as today's `_configure()`, minus the wrapper class)

- registers stdlib handlers: stdout (`_MaxLevelFilter(WARNING)`) and stderr (`setLevel(WARNING)`), both using `ProcessorFormatter`.
- foreign pre-chain: `add_logger_name`, `add_log_level`, `_resolve_pycord_bucket`, optional `TimeStamper(iso)` under `LOG_FORMAT=json`.
- final renderer: `JSONRenderer()` if `LOG_FORMAT=json`, else `ConsoleRenderer(colors=True, force_colors=True)`.
- structlog processors: `merge_contextvars`, `add_logger_name`, `add_log_level`, `PositionalArgumentsFormatter`, `StackInfoRenderer`, `format_exc_info`, optional iso `TimeStamper`, `wrap_for_formatter`.
- root level from `LOG_LEVEL` env or default `INFO`.
- pin `pymongo`, `aiohttp.access`, `discord.gateway` to WARNING.
- pin `discord.http` to `DEBUG if 'DEBUG' in environ else WARNING`.
- handler-marker idempotency (`_attu_owned`) so re-entry is a no-op.

what is NOT in configure():
- no custom levels (TRACE/ALERT registration goes away — see phase 2).
- no `AttubotLogger` class. no `_join`. no `_DEBUG_MODE` python-side gate.
- no `PycordBridgeHandler` marker; the bucket resolver runs in foreign pre-chain.

---

## phase 0 — walking skeleton

thinnest end-to-end slice that exercises every layer. derisks R1, R2, R3, R4, R9 simultaneously.

**scope:**
- create `packages/attu-logging/` with `configure()` and `webhook.send_to_webhook()`.
- add it as a workspace dep to `apps/bot`, `apps/chat`, `apps/server`, `packages/shared-models`.
- wire `apps/bot/doom-bot.py` to call `configure()` as line 1.
- wire `tests/conftest.py` to call `configure()` before any other repo import.
- flip exactly one shared-models module (`packages/shared-models/attu_models/connection.py`) to `structlog.stdlib.get_logger(__name__)`. leave `repositories.py` on the wrapper for now.
- flip exactly one app module (suggest `apps/bot/doom_bot/eggs/` since it's a clean leaf, 2 files) to the new path.
- leave the rest of the repo on the wrapper. the wrapper's own `_configure()` is still in place but skipped by the idempotency guard once `attu_logging.configure()` has run.
- add `tests/python/integration/test_attu_logging_contract.py`. this test file pins the phase-0 invariants directly so future regressions are caught by CI, not by hand-poking a container. it covers:
  - **R1 (configure-vs-import timing).** every handler on the root logger after `configure()` is tagged `_attu_owned`; no orphan handler created by a module-level `get_logger()` slipped in ahead.
  - **R3 (re-import idempotency).** calling `configure()` twice does not duplicate handlers, processors, or the foreign pre-chain.
  - **R4 (library-noise pin loss).** post-configure, `pymongo`, `aiohttp.access`, `discord.gateway` resolve to WARNING; `discord.http` resolves per the gate (covered separately by the unit gating test, but verify the pin is actually applied here).
  - **record shape.** emit a representative record through `structlog.stdlib.get_logger('attu_models.connection')` and assert the rendered string matches `^\\[(trace|alert|debug|info|warning|error|critical) *\\] ` under the default console renderer (this is the contract the `container-logs` skill relies on; pin it in code rather than via grep).
  - **shared-models logger via configure path.** import `attu_models.connection` and emit one info-level log; assert it goes through the configured pipeline (event captured by a `structlog.testing.capture_logs()` block or by a temporary stdlib handler installed for the test).

**definition of done:**
- `python scripts/run_tests.py` returns green (the wrapper shells out to `docker compose -f docker-compose.dev.yml run --build --rm --quiet-build tests` and runs unit + component + integration + vitest).
- `tests/python/integration/test_attu_logging_contract.py` exists, runs under the `integration` marker, and all of its cases pass — this is the test that pins R1/R3/R4 and the rendered-record shape so phase 0 cannot regress without CI catching it.
- `tests/python/integration/test_startup.py` continues to pass — it already exercises every module-level logger created during `_do_ready_init()` against real mongo with discord patched offline; if the configure-vs-import timing contract were broken, those startup loggers would be the first to misrender and the suite would fail.
- `tests/python/unit/test_logging.py` continues to pass — preserves `TestDiscordHttpLevelGating` (R9) and the rest of the existing unit surface.
- `grep -E 'from attu_logging' apps/bot/doom-bot.py` returns 1 line and it is the first non-comment import.

**cross-phase check (the one this DoD specifically guards):**
configure-vs-import timing (R1), re-import idempotency (R3), and library-noise pinning (R4) are all asserted by `tests/python/integration/test_attu_logging_contract.py`. the contract is pinned in code, not in tribal knowledge or container-log archaeology. one surface, one go/no-go: `python scripts/run_tests.py`.

---

## phase 1 — shared-models flip

derisks the original migration goal. small, contained.

**scope:**
- `packages/shared-models/attu_models/repositories.py` and any other shared-models file still importing `doom_bot.logging` switch to `structlog.stdlib.get_logger(__name__)`.
- replace any `logger.send_to_webhook(...)` site in shared-models (likely 0 today; verify) with `from attu_logging.webhook import send_to_webhook`.
- remove the "ambient import" comment from `packages/shared-models/pyproject.toml`.
- shared-models declares `attu-logging` as an explicit dep.

**definition of done:**
- `grep -rE 'from doom_bot.logging|import doom_bot.logging' packages/` returns 0 lines (Goal 1 met).
- `pyproject.toml` of `attu-models` lists `attu-logging` as a dep with no comment apologizing for it.
- `python scripts/run_tests.py` returns green (unit + component + integration + vitest).
- `tests/python/integration/test_startup.py` passes — `_do_ready_init()` exercises shared-models loggers post-flip against real mongo, so any rendering regression in `attu_models.*` surfaces here.
- extend `tests/python/integration/test_attu_logging_contract.py` (added in phase 0) with a case asserting that an `attu_models.repositories` logger emits through the configured pipeline.

**cross-phase check:**
the import graph is acyclic. `python -c 'import attu_models'` from a clean venv with only the shared-models + attu-logging packages installed (no `doom-bot`) succeeds.

---

## phase 2 — TRACE / ALERT removal

clears the most-special-cased path in the wrapper. R6.

**scope:**
- audit: `git grep -E 'logger\\.(trace|alert)\\(|TRACE|ALERT|addLevelName' apps/ packages/ tests/` → expect 2 call sites + the wrapper's registrations + maybe the test file.
- the alert call site in `apps/bot/doom_bot/commands/trees.py` becomes `logger.warning('trees_link: hmac rejected by server (401); check DISCORD_BOT_HMAC_SECRET', signal='hmac_rejected')`.
- the trace call site (one in `apps/chat/attu_chat/ingestor/...`) becomes `logger.debug(...)` if it should still be visible under DEBUG, or is deleted if it's narrative-only chatter.
- remove `addLevelName(TRACE)` and `addLevelName(ALERT)` calls from the wrapper.
- remove `_DEBUG_MODE` Python-side gate from the wrapper. the wrapper now routes `debug()` straight to structlog; level filtering is stdlib's job.
- update `tests/python/unit/test_logging.py`: drop the `test_trace_silent_without_debug_env` and `test_trace_emits_when_debug_set` cases; keep the rest.

**definition of done:**
- `git grep -E 'logger\\.(trace|alert)\\(|addLevelName.*(TRACE|ALERT)|_DEBUG_MODE'` returns 0 lines.
- `python scripts/run_tests.py` returns green.
- extend `tests/python/integration/test_attu_logging_contract.py` with assertions that no captured record under any logger has `level == 'trace'` or `level == 'alert'` (sanity: no level was inadvertently surfaced or buried by the conversion).

**cross-phase check:**
no record appears with `level: 'trace'` or `level: 'alert'` anywhere in the repo's test surface — pinned by the integration contract test extension above.

---

## phase 3 — `send_to_webhook` free function

R7. surface change that has to coordinate across 13 sites + the wrapper method.

**scope:**
- `attu_logging/webhook.py` already has `send_to_webhook(...)` from phase 0. confirm the signature matches today's `AttubotLogger.send_to_webhook`.
- update all 13 caller sites (audit: `git grep 'logger.send_to_webhook'` → expect ~13 lines across `events.py`, `scheduler.py`, `trees.py`, `wiki.py`, `debug.py`, `attu_chat/commands/ask.py`):
  - `await logger.send_to_webhook(err)` → `from attu_logging.webhook import send_to_webhook` + `await send_to_webhook(err, logger_name=__name__)`.
  - keep `location=` kwargs as-is.
- delete `AttubotLogger.send_to_webhook` from the wrapper.
- delete `apps/bot/doom_bot/webhook.py` (or move its contents into `attu_logging/webhook.py` if they aren't already there).

**definition of done:**
- `git grep 'logger.send_to_webhook'` returns 0 lines (Goal 4 met).
- `git grep 'send_to_webhook'` matches only the function definition + 13 callers.
- `python scripts/run_tests.py` returns green.
- add an integration test that triggers `send_to_webhook(...)` with the network call patched (same pattern as `test_db_error_triggers_shutdown` patches `_shutdown`) and asserts the request would have been built correctly. covers the migration end-to-end without depending on a live dev webhook endpoint.

**cross-phase check:**
removing the wrapper method does not cause any unrelated log site to break. `python scripts/run_tests.py` returns green against the partially-converted repo.

---

## phase 4 — bulk import-site conversion

derisks the longest, dullest part of the work. R10. one commit per directory.

**directory order** (leaf-first, smallest blast radius first):

| commit | dir | files | est. log sites touched |
|---|---|---|---|
| 4a | `apps/chat/attu_chat/ingestor/` | 11 | ~80 |
| 4b | `apps/bot/doom_bot/wiki/` | 6 | ~30 |
| 4c | `apps/bot/doom_bot/eggs/` | 2 | already done in phase 0 — skip |
| 4d | `apps/bot/doom_bot/web/` | 6 | ~30 |
| 4e | `apps/bot/doom_bot/tasks/` | 11 | ~70 |
| 4f | `apps/bot/doom_bot/commands/` | 12 | ~120 |
| 4g | `apps/bot/doom_bot/client/` | 12 | ~150 |
| 4h | `apps/bot/doom_bot/{webhook,signals}.py`, `apps/bot/doom-bot.py` | 3 | ~10 |

**per-commit scope:**
- `from doom_bot.logging import get_logger` → `import structlog`.
- `logger = get_logger(__name__)` → `logger = structlog.stdlib.get_logger(__name__)`.
- f-strings into kwargs **opportunistically** — when the structure is obvious (single-id interpolation, status flags, counts). leave purely-narrative strings alone. don't blow up the diff with marginal conversions.
- preserve `logger.warn` / `logger.fatal` aliases (structlog supports both).

**per-commit DoD:**
- `git grep 'from doom_bot.logging' <that-dir>/` returns 0 lines.
- `python scripts/run_tests.py` returns green (the integration suite reaches the converted modules during `_do_ready_init()` startup; a broken `get_logger(__name__)` swap fails there before any per-app subset). per-app subsets are still fine to run for fast feedback during the directory's commit, but the green CI run is the one that closes the per-commit DoD.

**phase-4 (overall) DoD:**
- `git grep 'from doom_bot.logging import get_logger'` returns exactly 1 line: the wrapper's own `__init__.py` re-export, if any.
- `git grep 'AttubotLogger\\b'` returns matches only inside `apps/bot/doom_bot/logging.py` and its test.

**cross-phase check:**
no converted record changes its level or logger name versus phase 3 — caught by the existing `capture_structlog`-based unit and component tests around each call site (any test that asserts on a log dict already pins this), plus the phase-0 integration contract test. if a per-directory commit silently regrades a record, the test that already covers that path fails. there is no "capture 200 records from the dev container" step — that was archaeology dressed as a check; the test suite is the ratchet.

---

## phase 5 — delete the wrapper

R8. nothing should still import it.

**scope:**
- `git rm apps/bot/doom_bot/logging.py`.
- `git rm tests/python/unit/test_logging.py` and create `tests/python/unit/test_attu_logging.py` covering the surface that survived: `_resolve_pycord_bucket`, `_MaxLevelFilter`, idempotency of `configure()`, discord.http level gating.
- update `tests/conftest.py`: `capture_structlog` fixture stays as-is; remove any wrapper-aware bits.
- `apps/bot/doom_bot/__init__.py`: remove any re-export of the wrapper symbols.
- update `notes/agents.md` if it still references the wrapper.

**definition of done:**
- `find apps/bot/doom_bot -name 'logging.py'` returns 0 paths (Goal 2 met).
- `git grep -E 'class AttubotLogger|PycordBridgeHandler'` returns 0 lines (Goal 2 met, second clause).
- `python scripts/run_tests.py` returns green (unit + component + integration + vitest).
- `tests/python/integration/test_attu_logging_contract.py` still passes after the wrapper deletion — proves `configure()` is the only configuration entrypoint and nothing in the bot startup path silently relied on the wrapper's import-time `_configure()` side effect.
- `tests/python/unit/test_attu_logging.py` (new in this phase, replaces `test_logging.py`) covers `_resolve_pycord_bucket`, `_MaxLevelFilter`, `configure()` idempotency, and `discord.http` level gating.
- all 5 goal-checks above pass on a single run.

**cross-phase check:**
`python scripts/run_tests.py` returns green — single surface, one go/no-go. the integration contract test added in phase 0 remains the ratchet that catches a configure-vs-import-timing regression.

---

## phase 6 — f-string sweep (optional)

opportunistic. not required for ship.

audit baseline: `git grep -E 'logger\\.[a-z]+\\(f["\\']'  | wc -l` (today: ~419). target: drive it down whenever a file is touched for other reasons. no dedicated commit; rolls in with whatever is already changing.

if the team wants a dedicated sweep, it's a separate plan with its own pre-mortem (mostly about review fatigue and regression risk on touched lines).

---

## risks summarized

| id | risk | phase that handles it | mitigation |
|---|---|---|---|
| R1 | configure-vs-import timing | 0 | configure as line 1 of every entrypoint; integration-check each phase |
| R2 | pytest bootstrapping | 0 | conftest.py calls `configure()` before any repo import |
| R3 | re-import idempotency | 0 | `_attu_owned` handler markers in `configure()` |
| R4 | library-noise pin loss | 0 | every pin from today's wrapper carried into `configure()` |
| R5 | `.warn` / `.fatal` aliases | — | non-issue; structlog supports both |
| R6 | `.trace` / `.alert` removal | 2 | convert 2 sites, drop registrations |
| R7 | `send_to_webhook` ordering | 0 + 3 | free function exists from phase 0; wrapper method outlives callers until phase 3 |
| R8 | phase-5 ordering | 4 + 5 | phase-4 DoD greps for any remaining wrapper imports |
| R9 | discord.http regression | 0 (via tests) | `TestDiscordHttpLevelGating` moves to `test_attu_logging.py` in phase 5; pinned by green CI |
| R10 | phase 4 diff size | 4 | split into 8 directory-scoped commits |
| R11 | webhook.py home (D3) | 0 | committed: `attu_logging/webhook.py`. revisit only on retro |

---

## minimum viable adoption?

no. this plan is 5+ phases, cross-package, cross-process. full loop applies: pre-mortem (above), `feature-completion` + `code-review` + `integration-check` per phase, `phase-retro` between phases, `bug-triage` to gate bug-log → next-phase, `plan-revise` after each retro. `ship-readiness` before declaring done.

---

## post-phase-0 — 2026-05-10

### retro

**spec delta.** clean match. all DoD items landed: `attu_logging` package with `configure()` + `send_to_webhook()`; configure-as-line-1 in `apps/bot/doom-bot.py` and `tests/conftest.py`; three modules flipped to direct structlog (`attu_models/connection.py`, `eggs/emojis.py`, `eggs/hatching.py`); workspace dep wired across all four consumers; the new contract test (10 cases) pins R1/R3/R4 + record shape; wrapper coexistence via `_doom_bot_owned` marker works. **extra:** mid-phase plan revision (phase 0 + downstream DoDs) to remove prod-compose / `core` references after the user flagged the anti-pattern; Dockerfile chmod +x at `apps/bot/Dockerfile:105` (pre-existing infra bug that blocked the wrapper); `AttubotLogger.warning = warn` alias at `apps/bot/doom_bot/logging.py:198` (pre-existing wrapper bug surfaced once tests could run).

**surprises.** the plan's phase-0 DoD command had not been tried — it referenced prod compose against a service (`core`) that doesn't exist in dev. `python scripts/run_tests.py` had been broken on dev for at least one commit cycle (chmod missing); two pre-existing bugs were masking each other (the wrapper missing `.warning` was hidden because the wrapper-runner couldn't run). the contract test's "every root handler is `_attu_owned`" assertion immediately false-positived on pytest's own LogCaptureHandlers; rewrote it in terms of `structlog.get_config()['wrapper_class']` + "at least one `_attu_owned` handler exists." cheap surprise: dual-marker coexistence (`_attu_owned` + `_doom_bot_owned`) made the wrapper-bypass a one-line idempotency guard, no refactor needed.

**residual debt.** none deferred. the dual-marker hack at `attu_logging/config.py:110-128` is already inline-flagged for phase 5 removal. the legacy wrapper itself remains by design until phase 5. ~419 f-string sites await phase 6.

### plan revision

**what changed:**
- phases 1, 2, 3, 4, 5, 6: **valid** — all downstream phases hold as written. the contract test added in phase 0 (`tests/python/integration/test_attu_logging_contract.py`) is the ratchet for R1/R3/R4 across phases 1-5; the prod-compose / `core` anti-pattern was already removed mid-phase-0.

**heads-up for whoever picks up the next phase** (not spec changes — the plan stands):
- before phase 4 starts, grep `logger\.(warning|fatal|warn)\b` to inventory legacy-stdlib-method call sites. risk is now low — the wrapper has both `.warn` and `.warning` after the in-flight fix, and structlog `BoundLogger` supports both natively post-conversion — but the inventory protects against an unknown legacy method (e.g. `.exception`) that the wrapper might also be missing.
- phase 5 will remove the `_doom_bot_owned` legacy markers from `attu_logging/config.py:110-128` (already inline-flagged) along with the wrapper itself.
- the `apps/bot/Dockerfile` chmod +x hunk is unrelated to the structlog migration; it stays after phase 5's wrapper deletion.

bug log: empty. the two pre-existing bugs surfaced (`scripts/run_tests.py` chmod, `AttubotLogger.warning` alias) were fixed in-flight as DoD prerequisites, not deferred.

---

## post-phase-1 — 2026-05-10

### retro

**spec delta.** clean match. `packages/shared-models/attu_models/repositories.py` flipped to direct structlog (the only shared-models file still on the wrapper after phase 0); apologetic comment removed from `packages/shared-models/pyproject.toml`; contract test extended with `test_attu_models_repositories_logger_routes_through_structlog`. Goal 1 grep-clean. Cross-phase check (`import attu_models` from a doom_bot-free PYTHONPATH inside the tester container) succeeded — the cycle is broken at runtime.

**surprises.** plan implied multiple shared-models files needed flipping; only `repositories.py` did. structlog `BoundLogger.warn` is a stdlib alias and worked unchanged for the 6 `logger.warn(...)` call sites in `StarboardRepository`, so no per-call-site edits were needed. the cross-phase "no cycle" check turned out to be a one-shot `PYTHONPATH=...` invocation inside the existing tester container, not the venv-gymnastics the plan implied. carried-forward question from phase 0 (whether the `AttubotLogger.warning` bandaid was load-bearing for repositories.py) confirmed no — repositories used `.warn`, not `.warning`.

**residual debt.** one item, not structlog-scope: the TYPE_CHECKING-only `from doom_bot.config import BotTheme, GuildConfig` in `repositories.py:36`. doesn't violate the runtime cycle rule (cross-phase check confirmed) but is an architectural smell. **routed to `notes/bugs.md`** under `architecture` section as `nit / defer`; would require either moving `BotTheme`/`GuildConfig` into shared-models or generalizing the repo signatures to protocols — separate plan, not a structlog phase.

### plan revision

**what changed:**
- phases 2, 3, 4, 5, 6: **valid** — phase 1 didn't move any premise. all downstream phases hold as written.

**heads-up for whoever picks up the next phase** (not spec changes — the plan stands):
- phase 3 confirmed: shared-models has zero `send_to_webhook` callers (verified during phase 1's audit grep). phase 3's scope of "13 sites in events.py, scheduler.py, trees.py, wiki.py, debug.py, attu_chat/commands/ask.py" is the complete set; no surprise sites lurking in shared-models.
- phase 4 risk further reduced: structlog `BoundLogger.warn` / `.warning` interchangeability now demonstrated end-to-end through `repositories.py`. the pre-phase-4 grep is still worth doing, but the failure mode it was guarding against (a method the wrapper had but structlog doesn't) is empirically absent for the warn family.

bug log (structlog plan): empty. one item routed to project-wide `notes/bugs.md` under `architecture` (defer).
