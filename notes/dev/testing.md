# Testing overview

AttuBot uses pytest for python tests and vitest for javascript tests. All test files live under `tests/`, which is treated as a python package (see `tests/__init__.py`).

## Directory layout

- `tests/python/unit/` hosts fast python unit tests that only mock external services.
- `tests/python/component/` runs against a live MongoDB but still mocks Discord/wiki clients when possible. These tests are decorated with `pytest.mark.component` and rely on the component fixtures defined in `tests/conftest.py`.
- `tests/python/integration/` contains higher-level scenarios (currently the startup readiness check). Integration tests are marked with `pytest.mark.integration`.
- `tests/js/unit/` contains the vitest suites that focus on frontend helpers and do not require Python resources.

File names follow the convention `test_<feature>.py` for python and `<feature>.test.js` for vitest. The folder name carries the scope, so there is no need to suffix filenames with `_unit`, `_component`, etc.

## Fixture & marker guidance

- Shared fixtures live in `tests/conftest.py`. `component_db` connects to the configured MongoDB url, prefixes collections per test, and drops them during teardown.
- Component tests set `pytestmark = pytest.mark.component` near the top of the module. Integration tests use `pytestmark = pytest.mark.integration`.
- Unit tests should avoid touching live MongoDB/Discord by using the provided repo mocks and `mock_ctx_factory` for command contexts.

## Running tests

Run all tests inside the test container. If needed, other commands can be swapped out in place of the script. Do not remove other arguments.
```
docker compose run --build --rm --quiet-build tests scripts/run_tests.py
```

1. **Python unit/component/integration**
   ```bash
   TZ=UTC python -m pytest -m not integration
   TZ=UTC python -m pytest -m component
   TZ=UTC python -m pytest -m integration
   ```
   (The `TZ=UTC` ensures deterministic calendar behavior and matches the test runner expectation.)

2. **Javascript**
   ```bash
   npm run test
   ```
   Vitest picks up `tests/js/unit/*.test.js` thanks to `vitest.config.js`.

3. **Combined helper**
   ```bash
   python scripts/run_tests.py
   ```
   This script orchestrates coverage, python suites, and vitest. Pass `--coverage` to print the coverage report to stdout.

## Coverage & troubleshooting

- Coverage reports target `attubot/` plus the python tests (see `scripts/run_tests.py` and `coverage` config). If you add new files, ensure the `coverage run` command still wraps the desired modules.
- If MongoDB is unavailable, component tests will fail quickly; make sure `assets/attu-bot.toml` points to a reachable instance before running them.
- `TZ=UTC` must be set before pytest starts because `attubot.config` reads the timezone at import time. The shared `tests/conftest.py` already sets it for every test.
- When renaming tests, keep imports (e.g., `from tests.conftest import TEST_GUILD`) relative to the test package layout.

## Mock compensation

The mock compensation rule, the three standing cases (extension loading, permission checks, migrations), and the general principle now live in the `mock-compensation` skill (`.claude/skills/mock-compensation/SKILL.md`). The skill is canonical; update it rather than this file.

## Next improvements

- Expand integration coverage by spinning up each Quart route group behind mocked dependencies instead of patching internals. The startup integration test currently covers the overall bot/web ready path and can serve as a template.
- Consolidate any remaining heavy mocks into fixtures so additional suites can share them without duplicating setup code.

---

## metadata

```yaml
last_updated: 30 March 2026
```
