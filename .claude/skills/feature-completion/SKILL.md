---
name: feature-completion
description: AttuBot end-of-task checklist - tests, documentation, configuration plumbing, admin api, and linting. trigger when the user signals task wrap-up ("ready to commit", "feature done", "ready for review", "I think that's it", "done", "looks good"); when running pytest, ruff check, ruff format, or `scripts/run_tests.py`; before drafting any `git commit` message; before reporting a feature, fix, or refactor as complete. canonical source for the checklist; the numbered rules in `CLAUDE.md` take precedence over anything here.
---

# feature completion checklist

walk through every applicable item below before reporting a task as done. answer each as a literal yes/no; if the answer is no and the item applies, finish that item before declaring completion.

rules referenced below are the numbered list in `CLAUDE.md`.

## tests

- [ ] did you add or update unit tests for the new logic in `tests/python/unit/`?
- [ ] did you add component tests for any new repository methods or DB operations in `tests/python/component/`?
- [ ] did you add a new file under `apps/bot/nova_core/commands/`? if yes, does `TestExtensionImports.test_extension_imports_cleanly` in `tests/python/unit/test_start_bot_loop.py` still pass? (mock compensation rule; see the `mock-compensation` skill for the full rationale)
- [ ] did you add new `@commands.check` predicates? if yes, did you add or update predicate tests in `tests/python/unit/test_util.py`? (mock compensation rule)
- [ ] did you add a new migration in `nova_core/client/migrations.py`? if yes, did you add a rollback path test before merging?
- [ ] did you add a new config field? if yes, did you add a roundtrip test that saves a non-default value, reloads via `load_guild()`, and asserts it survives?
- [ ] did you run the full suite and is it green? primary path is the venv: `uv run python scripts/run_tests.py` (component suites need `docker compose -f docker-compose.dev.yml up -d mongo` and `TEST_DB_URL`; see README "tests"). the docker `tests` service covers unit and component only

## documentation

- [ ] did you update the relevant feature spec in `docs/features/` if behavior or storage changed? bump `last_updated` in its metadata block
- [ ] did you add or remove a slash command? if yes, update the command list in `README.md` and the commands table in `docs/architecture.md`
- [ ] did you add a new admin api route or `nova_admin` subcommand? if yes, update the "admin api" table in `README.md` and the `api/admin/` row in `docs/architecture.md`
- [ ] is the feature new, stable, and referenceable? if yes, add a spec under `docs/features/` and a nav entry in `mkdocs.yml`
- [ ] did you update `docs/to-do.md` to reflect completed work, and `docs/bugs.md` for anything you found but did not fix?

## configuration (only if you added a config field)

- [ ] did you pick the right tier? (`.env` for the config-file path only; TOML for static secrets and startup values; MongoDB for per-guild operator-adjustable values). see `docs/config-system.md`
- [ ] **tier 2 (TOML):** did you add the field to the relevant Pydantic model in `apps/bot/nova_core/config.py`?
- [ ] **tier 2 (TOML):** did you add a sensible placeholder in `config/attu-bot.sample.toml`?
- [ ] **tier 2 (TOML):** did the TOML format change shape? if yes, bump `__config_version__` in `nova_core/__init__.py`; if only defaults changed, leave it
- [ ] **tier 3 (MongoDB):** did you complete all three plumbing steps? missing any one causes the field to silently use its default in production:
  1. [ ] `packages/shared-models/attu_models/documents.py` - field added to `GuildConfigDocument` with a default
  2. [ ] `apps/bot/nova_core/config.py` - field added to the runtime `GuildConfig` model with the same default
  3. [ ] `apps/bot/nova_core/config.py` - field passed explicitly when constructing `GuildConfig` in `NovaConfig.load_guild()`
- [ ] **tier 3:** the admin api patches any dotted key generically (`PATCH /admin/guilds/{slug}/config/{key}`) and validates against `GuildConfigDocument`, so no per-field route work is needed; if the field holds a channel or role id, confirm its name ends in `_channel` or `_id` so slug resolution kicks in
- [ ] **tier 3:** did you add the roundtrip test (also covered under tests above)?
- [ ] does the field gate a feature? if yes, add it to `_FEATURE_FIELDS` in `apps/server/attu_server/api/admin/features.py` so the enable/disable routes accept it; those routes save the field and trigger a guild reload (`config.load_guild()` via the bridge), so confirm the gated code reads the reloaded `GuildConfig` rather than a value cached at startup

see the `pydantic` skill for the document/runtime model split, `ConfigDict(extra='ignore')`, and validator patterns covering the same ground.

## admin api (only if you added or changed attu_server routes or bridge ops)

- [ ] new admin route registered under the `/admin` router (`apps/server/attu_server/api/admin/__init__.py`) so the api-key dependency applies?
- [ ] every mutation: does it call `bridge.trigger_reload(...)` (and `bridge.invalidate_guild_cache()` for guild config) after saving so the bot process picks up the change?
- [ ] bot-side work goes in a bridge ops endpoint (`nova_core/bridge/router.py`, signed router) with a matching server route in `api/admin/ops.py` and a `scripts/nova_admin.py` subcommand?
- [ ] errors raised as `HTTPException` with a useful `detail`; successes return a plain dict
- [ ] are Discord snowflake IDs serialized as strings in JSON responses to avoid JavaScript precision loss?
- [ ] unit tests for the new route in `tests/python/unit/` (see `test_admin_ops.py`, `test_admin_config.py` for the pattern)?

## linting

- [ ] is `uv run ruff check .` clean for the files you touched? (the repo carries pre-existing debt from the expanded rule set; do not add to it, do not suppress without cause)
- [ ] is `uv run ruff format --check .` clean for the files you touched?
- [ ] every `# noqa` suppression has a valid reason attached? (rule #4)
- [ ] no em-dashes in anything you wrote (grep the diff for U+2014)

## final gate

- [ ] every applicable box above is checked
- [ ] you have not pushed or deployed without explicit user instruction (rule #3); local commits inside a worktree branch are fine
