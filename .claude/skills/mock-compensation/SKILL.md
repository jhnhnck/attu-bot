---
name: mock-compensation
description: AttuBot's mock compensation rule - when a test mocks a framework mechanism, it owes a real test elsewhere that exercises the mocked behavior. trigger when editing or creating files under tests/python/, when adding new files under doom_bot/commands/, when adding new predicates to doom_bot/client/util.py, or when adding new migrations to doom_bot/client/migrations.py.
---

# mock-compensation

**the rule:** when a test mocks a framework mechanism, it inherits responsibility for the behavior that mock hides; cover that behavior at another level or the failure mode is silent green CI. this skill is canonical; see also [`docs/dev/testing.md`](docs/dev/testing.md) for surrounding test conventions (fixtures, layout, running tests).

silent test passage is the worst failure mode. a mock that hides a broken decorator, a missing import, or a skipped permission check turns a real prod bug into a green checkmark. every mock of a framework mechanism owes a compensating test somewhere else.

## standing cases

### 1. extension loading

- **mocked in:** [`tests/python/unit/test_start_bot_loop.py`](tests/python/unit/test_start_bot_loop.py) — `bot.load_extension()` is mocked to verify call orchestration.
- **what the mock hides:** import-time evaluation of every command module. decorators (`@discord.slash_command`, `@commands.check`, etc.) run at import; a missing import or attribute error never reaches the orchestration test.
- **compensation:** `TestExtensionImports.test_extension_imports_cleanly` ([`tests/python/unit/test_start_bot_loop.py:350`](tests/python/unit/test_start_bot_loop.py#L350)) does a real `importlib.import_module()` for every entry in `doom_bot.extensions_list`.
- **trigger:** any new file added under [`doom_bot/commands/`](doom_bot/commands/) — confirm the module is in `doom_bot.extensions_list` and that this test still passes before merging.

### 2. permission checks

- **bypassed in:** every command test under [`tests/python/unit/`](tests/python/unit/) calls command callbacks directly; `@commands.check(predicate)` decorators never run.
- **what the mock hides:** the predicate functions themselves (`is_bot_owner`, `is_authorized_guild`, `has_announcements_role`). a broken predicate would still let every command test pass while gating prod traffic incorrectly.
- **compensation:** predicate tests in [`tests/python/unit/test_util.py`](tests/python/unit/test_util.py) exercise each predicate against real config state (true and false cases).
- **trigger:** any new predicate added to [`doom_bot/client/util.py`](doom_bot/client/util.py), or any existing predicate applied to a new command — add corresponding true/false tests in `test_util.py`.

### 3. migrations

- **what the gap is:** migration code paths only run end-to-end on real db state during deploy; a broken migration shows up in prod.
- **compensation:** for every new entry in [`doom_bot/client/migrations.py`](doom_bot/client/migrations.py), add a rollback path test in [`tests/python/unit/test_migrations.py`](tests/python/unit/test_migrations.py) before merging.
- **trigger:** any new `@migration(...)` decorator added to `doom_bot/client/migrations.py`.

## general principle

before mocking anything framework-y (decorators, lifecycle hooks, plugin loaders, signal handlers, middleware), ask:

1. **what behavior does this mock hide?** name it concretely - "decorator evaluation at import," "the actual permission check," "the pre-save hook that normalizes the field."
2. **is that behavior covered elsewhere?** find the test that exercises it for real, or the integration that would catch a regression.
3. **if not, the test you're writing isn't complete yet.** add the compensating test in the same change, or the gap ships with the feature.

write the answer down in the test docstring; future readers (including the model) need to see the chain.
