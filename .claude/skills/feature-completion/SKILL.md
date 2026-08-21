---
name: feature-completion
description: AttuBot end-of-task checklist - tests, documentation, configuration plumbing, web interface, and linting. trigger when the user signals task wrap-up ("ready to commit", "feature done", "ready for review", "I think that's it", "done", "looks good"); when running pytest, ruff check, ruff format, npm run lint, or `docker compose run ... tests`; before drafting any `git commit` message; before reporting a feature, fix, or refactor as complete. canonical source for the checklist - if it diverges from `docs/agents.md`, this skill wins.
---

# feature completion checklist

Walk through every applicable item below before reporting a task as done. Answer each as a literal yes/no; if the answer is no and the item applies, finish that item before declaring completion.

Source section: `docs/agents.md` — `## feature completion checklist`. This skill is canonical; if it drifts from agents.md, flag the divergence so agents.md gets updated to match.

## tests

- [ ] did you add or update unit tests for the new logic in `tests/python/unit/`?
- [ ] did you add component tests for any new repository methods or DB operations in `tests/python/component/`?
- [ ] did you add a new file under `doom_bot/commands/`? if yes, does `TestExtensionImports.test_extension_imports_cleanly` still pass? (mock compensation rule; see the `mock-compensation` skill for the full rationale)
- [ ] did you add new `@commands.check` predicates? if yes, did you add or update predicate tests in `test_util.py`? (mock compensation rule)
- [ ] did you add a new migration in `client/migrations.py`? if yes, did you add a rollback path test before merging?
- [ ] did you add a new config field? if yes, did you add a roundtrip test that saves a non-default value, reloads via `load_guild()`, and asserts it survives?
- [ ] did you run the full suite via `docker compose run --build --rm --quiet-pull tests` and is it green?

## documentation

- [ ] did you update the relevant feature spec in `docs/features/` if behavior or storage changed?
- [ ] is the feature new, stable, and referenceable? if yes, did you propose a new note file following `docs/.meta.md` guidance (feature.md, library_usage.md, or domain_concept.md)?
- [ ] if you added a new note file, did you update the reference notes table in `docs/agents.md`?
- [ ] did you update `docs/to-do.md` to reflect completed work?

## configuration (only if you added a config field)

- [ ] did you pick the right tier? (`.env` for the config-file path only; TOML for static secrets and startup values; MongoDB for per-guild operator-adjustable values)
- [ ] **tier 2 (TOML):** did you add the field to the relevant Pydantic model in `doom_bot/config.py`?
- [ ] **tier 2 (TOML):** did you add a sensible placeholder in `config/attu-bot.sample.toml`?
- [ ] **tier 3 (MongoDB):** did you complete all six plumbing steps? missing any one causes the field to silently use its default in production:
  1. [ ] `doom_bot/database/models.py` - field added to `GuildConfigDocument` with a default
  2. [ ] `doom_bot/config.py` - field added to the runtime `GuildConfig` model with the same default
  3. [ ] `doom_bot/config.py` - field passed explicitly when constructing `GuildConfig` in `NovaConfig.load_guild()`
  4. [ ] `doom_bot/web/forms.py` - field added to `GuildConfigForm` so web saves don't drop it
  5. [ ] `assets/templates/guild_config.html` - form control added
  6. [ ] `assets/static/js/app.js` - `populateField('field_name', data.field_name)` added in `loadGuildConfig()`
- [ ] **tier 3:** did you add the roundtrip test (also covered under tests above)?
- [ ] does the field gate an extension? if yes, did you handle the `False → True` transition in the activating task (`bot.reload_extension()` + `bot.sync_commands()`) and diff old vs. new in `tasks/reload_watcher.py` so web-triggered changes apply without a restart?

See the `pydantic` skill for the document/runtime model split, `ConfigDict(extra='ignore')`, and validator patterns covering the same ground.

## web interface (only if you added or changed web-facing config, pages, or endpoints)

- [ ] did you follow the relevant guide in `docs/features/web.md` (adding a config field; adding a page or endpoint)?
- [ ] every mutation: did you add audit logging via `web_app.audit_logger.log_change(...)`?
- [ ] every mutation: did you send a reload signal via `send_signal()` after save so the bot process picks up the change?
- [ ] new API endpoints: do they return `{'error': '...'}` on failure and `{'success': True, 'message': '...'}` on success?
- [ ] are Discord snowflake IDs serialized as strings in JSON responses to avoid JavaScript precision loss?

## linting

- [ ] is `ruff check .` clean? (fix all issues; do not suppress without cause)
- [ ] is `ruff format --check .` clean?
- [ ] did you touch any JS? if yes, is `npm run lint` clean?
- [ ] every `# noqa` suppression has a valid reason attached? (rule #4 from `docs/agents.md`)

## final gate

- [ ] every applicable box above is checked
- [ ] you have not run `git commit` without explicit user instruction (rule #3 from `docs/agents.md`)
