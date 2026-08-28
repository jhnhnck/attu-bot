# pre-mortem - venv-tests

**bottom line:** proceed with revisions - two medium risks, both retired by probes in phase 0 before any code changes.

---

### risks

- [medium] integration - integration tests' behavior outside Docker is unknown; they may test bot startup (needs `TEST_MODE`), call Discord API, or import something container-specific; phase 1 DoD requires all three suites to pass, but phase 0 only validates one component test; if integration tests fail for non-DB reasons, phase 1 appears broken even though the DB fix worked - probe: run `python -m pytest tests/python/integration/ -v` from venv in phase 0 and document failures before writing code

- [medium] premise - conftest assumes `.secrets/attu-bot.toml` has `[database].url` and `[database].name` keys; if the TOML uses different section names, `_read_db_config()` throws `KeyError` and falls through to the Docker-internal default silently - probe: `python -c "import tomlkit; d=tomlkit.load(open('.secrets/attu-bot.toml')); print(d.get('database'))"` in phase 0

- [low] scope - worktrees don't have `.secrets/attu-bot.toml`; existing to-do covers this; plan mentions `ATTU_CONFIG_FILE` but the worktree workaround needs explicit documentation - addressed in phase 2 docs

- [low] dependency - `coverage` CLI must be in the dev venv; container had it; venv may not - probe: `python -m coverage --version` in phase 0

---

### walking-skeleton check

**verdict: correct.** phase 0 adds the `mongo` service and runs one component test end-to-end — touches compose, the DB connection path, and venv execution in one step. no code changes until it passes.

one gap: phase 0 only validates component tests, not integration. added integration probe to phase 0 so failures are documented before phase 1 starts.

---

### phase-order revisions

no reordering needed. phase 0 (add mongo service + validate) -> phase 1 (code fix) -> phase 2 (docs) is correct risk-first order.

---

### definition-of-done additions

- phase 0 - add: integration test venv probe documented; TOML `[database]` section confirmed; `coverage` in venv confirmed
- phase 2 - add: worktree `ATTU_CONFIG_FILE` workaround documented; project-level settings.json (not global)
