# bugs — nova-w1: structural prerequisites
## open

- [defer] bridge startup wiring (`start_bridge_task()` called from `_do_ready_init()` after the `test_mode` guard) has zero test coverage: every integration test in `test_startup.py` uses `test_mode=True` which returns before reaching the bridge block; `test_bridge_auth.py` calls `build_app()` directly, bypassing the ready path. a compensating test would need to use `test_mode=False` and mock uvicorn (or `start_bridge_task`) to assert the call was made without actually binding a port. apply mock-compensation skill when adding this test.

- [defer] `notes/` docs still reference `apps/bot/doom_bot/` paths in prose descriptions (agents.md, features/*.md, dev/testing.md, style/*.md, nova-core.md); these are cosmetic doc accuracy issues; ruff clean (docs are not .py); update gradually as each feature doc gets edited for other reasons
- [defer] `notes/bugs.md:26` still references `doom_bot.config.{BotTheme, GuildConfig}` in its description of a pre-existing coupling smell; the actual import in `attu_models/repositories.py` was fixed in phase 1 to `nova_core.config`; the bugs.md entry text is now stale history, not an active bug
- [defer] `tests/python/unit/test_start_bot_loop.py` and `tests/python/integration/test_startup.py` use `patch.object(nova_core.bot, ...)` and `isinstance(nova_core.bot, discord.Bot)` patterns which access `nova_core.bot` as a live python object; `nova_core/__init__.py` does not re-export `bot`; confirmed still present after phase 1 (cab68f3 fixed the same pattern in test_commands_stars, test_messages, test_starboard but not these two files); in pre-existing unit/integration baseline, not blocking component tests; fix requires switching callers to `nova_core.client.core.bot`; defer to a later pass

- [defer] `tests/python/unit/test_start_bot_loop.py::TestSetupDiscordLogging::test_sets_discord_http_logger_to_debug` asserts `discord.http` level is unconditionally `DEBUG` but `_setup_discord_logging()` has been conditional (`DEBUG in environ`) since at least d16d1b2 (pre-phase-2); test predates the conditional and was already failing before the migration; `TestDiscordHttpLevelGating` in `test_logging.py` covers both branches correctly with monkeypatch; fix is to update the stale test or delete it in favor of the better coverage in test_logging.py
- [defer] vestigial `mock_logger.send_to_webhook = AsyncMock()` assignments in `test_task_error_hook.py`, `test_task_logo_update.py`, `test_scheduler.py`, and `test_task_presence.py`; these mocked a method that no longer exists on `structlog.stdlib.BoundLogger`; no assertion checks the attribute so the lines are dead but harmless; correct fix is to delete the dead assignments or replace with `patch('attu_logging.webhook.send_to_webhook', ...)` if the call is meaningful to the test
- [defer] `nova_core/client/events.py` `_do_ready_init()`: add explanatory comment at the `set_webhook_url` call site noting that if `on_load()` raises before reaching this line, the except-clause `send_to_webhook()` silently no-ops (url unset); behavior unchanged from pre-migration; non-blocking comment-only fix
- [defer] `_break_at_newline` inlined into `attu_logging/webhook.py` creates drift risk vs `nova_core/client/util.py`; real fix is moving to a shared-models package; out of scope for nova-w1; track in workstream 3

## closed
- em-dashes throughout `plan.md` and `log.md`; fixed in phase 1 close pass (plan.md edited for plan-revise, triggering the deferred condition)

## phase 2 — newly visible pre-existing failures

### test_bridge_sign.py — 5 tests need uvicorn/attu_server (not in unit container)

- **tests:** `test_sign_symmetry_get`, `test_sign_symmetry_post_with_body`, `test_sign_changes_with_body`, `test_sign_changes_with_method`, `test_sign_method_case_insensitive`
- **root cause:** `nova_core/bridge/router.py` imports `uvicorn` at module level; `test_bridge_sign.py` imports `nova_core.bridge.hmac` and `nova_core.bridge.router`; unit container lacks uvicorn; two tests also import `attu_server` which is server-only
- **phase 2 relation:** pre-existing; masked in phase 0-1 by `test_bridge_auth.py` collection error stopping the unit suite before reaching `test_bridge_sign.py`; visible now only because integration-check re-ran with `--ignore=test_bridge_auth.py`
- **classification:** resolved in phase 3: `import uvicorn` made lazy in `router.py`; `bridge/__init__.py` cleared of re-exports to break the import chain; `hmac.py` uses `contextlib.suppress(ImportError)` for fastapi; `test_bridge_sign.py` uses `pytest.importorskip` for the two attu_server symmetry tests. result: 3 pass, 2 skip (attu_server not installed locally -- correct).
