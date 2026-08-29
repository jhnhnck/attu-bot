# venv-tests

## goals

1. `python scripts/run_tests.py` runs all python suites from the project venv without docker, pointing at a `mongo:8` container started via dev compose
2. `ATTU_CONFIG_FILE` (or `TEST_DB_URL`) is the documented canonical way to point tests at a db from any context
3. CLAUDE.md sub-agent rule narrowed: "do not run docker commands" stays; "do not run tests" replaced with explicit venv-safe test command that main agent may use
4. `settings.json` allows `python scripts/run_tests.py` and `pytest tests/` without prompt
5. README.md's "tests" section reflects the venv workflow: which suite needs what, docker vs local, `ATTU_CONFIG_FILE`/`TEST_DB_URL` as the canonical db pointer - docker one-liner is no longer the only documented path
6. `mock-compensation` skill paths updated from `doom_bot` to `nova_core`

## non-goals

- converting component tests to unit tests (separate to-do, `docs/to-do.md` "testing" section already tracks this)
- mongo-cutover compose cleanup (auth, replica set, ferret/postgres removal - that plan handles it)
- adding `--config` CLI arg to `run_tests.py` (env var already covers this)
- fixing the docker-path integration test gap (`tests` service has had no `.secrets` mount and no `ATTU_CONFIG_FILE` since `36f6fee`, 2026-08-02) - docker-path problem, unrelated to this venv-focused plan; parked in `bugs.md`
- fixing `.env`'s `ATTU_CONFIG_FILE` pointing at a nonexistent `./assets/attu-bot.toml` - separate misconfiguration; parked in `bugs.md`
- recreating `docs/dev/testing.md` - deliberately deleted in `49d2e88` (2026-08-24, "chore(docs): delete obsolete dev guides"); this plan documents in README instead, not in a resurrected dev-guide directory

## constraints

- runs before mongo-cutover; this plan adds a standalone `mongo:8` service to dev compose with an exposed port, no auth, no replica set; mongo-cutover's phase 1 already independently plans a `mongo` service with replSet + auth + `mongo-init` - same service name, deliberately additive, mongo-cutover absorbs and extends this one later. **once this plan lands, `mongo-cutover/plan.md` phase 1's scope line ("add mongo service...") needs a pending edit to "extend the existing mongo service..." - not done here, flagged to the user at merge time**
- no auth on the test mongo container (mongo-cutover adds auth); `TEST_DB_URL=mongodb://localhost:27017/doombot` is sufficient for this plan
- `_PrefixedDB` with `uuid4` prefix already provides parallel isolation across worktree runs - no changes needed (confirmed still present, `tests/conftest.py:426,459`)
- coverage source paths in `pyproject.toml` are already correct (`apps/bot/nova_core`, `packages/shared-models/attu_models`) - not touched (confirmed, `pyproject.toml:155`)
- JS test files and artifacts already removed from the repo; `run_tests.py` already doesn't run vitest in its suites list. **revised: the cleanup is bigger than "one stale comment"** - `scripts/run_tests.py` still has a vitest reference in `extract_counts()`'s docstring and a strip comment (line 26, 31), and `tests/python/unit/test_run_tests.py` has three whole methods named around vitest output shape (`test_vitest_single_suite`, `test_vitest_multi_suite`, `test_vitest_with_failures`, lines 78/82/86) - phase 1 needs to decide whether those tests still earn their keep as regex-generality checks or should go
- a worktree does not carry `.secrets/` (gitignored, not copied by `git worktree add`) - the plan's phase 2 workaround (point `ATTU_CONFIG_FILE` at the main checkout's copy, or symlink) is the only way integration tests find a config file from a worktree; confirmed by direct check in this worktree (`.secrets` absent)

## accepted risks

no auth on the test container simplifies the connection string; mongo-cutover adds auth later.

two pre-mortem risks from the original draft, both now partially retired by direct verification (2026-08-28) rather than left for phase 0 to discover cold:

- **integration test behavior outside docker**: main checkout's `.secrets/attu-bot.toml` has `config_version = "2.6.0"` against a required `2.8.0` (`nova_core/config.py`'s `__config_version__`). phase 0's integration probe *will* hit a `ConfigLoadError` version-gate rejection - this is pre-existing local-secrets staleness, not a bug introduced by this plan or a docker-vs-venv difference. phase 0 must document this explicitly so it isn't misattributed; either bump the local secrets file's `config_version` before probing, or record the expected failure as known-stale-secrets and move on.
- **TOML `[database]` key names**: same file's `database.url` is `mongodb://...@ferret:27017/...` - a docker-only hostname. `tests/conftest.py`'s `_read_db_config()` checks `TEST_DB_URL` first, so this most likely doesn't block phase 0's component-test proof - but `config.on_init()` (the path integration tests exercise) may read `database.url` directly rather than `TEST_DB_URL`. not reproduced; phase 0's probe step should confirm which path `config.on_init()` actually takes before assuming it's fine.

---

### phase 0 - walking skeleton

**scope:** add `mongo:8` service to dev compose with exposed port; prove one component test passes from venv against it; probe (don't fix) integration test behavior.

- add `mongo` service to `docker-compose.dev.yml`: `image: mongo:8`, `ports: ["27017:27017"]`, no auth, no replica set (mongo-cutover adds both); named `mongo` so mongo-cutover's later additions are additive - **echo: this is the cross-plan constraint mongo-cutover phase 1 depends on; do not rename**
- `docker compose up -d mongo` to start it
- run one component test from venv: `TEST_DB_URL=mongodb://localhost:27017/doombot python -m pytest tests/python/component/test_db_repositories.py -x -m component -k "test_config"` (or any small, fast test)
- before probing integration tests: check the local `.secrets/attu-bot.toml`'s `config_version` - if still below `2.8.0`, either bump it or note the expected version-gate failure up front so it isn't logged as a phase-0 regression
- probe integration tests from venv: `python -m pytest tests/python/integration/ -v`; document any failures and root cause, specifically noting whether `config.on_init()` reads `TEST_DB_URL` or `database.url` from the toml
- confirm `coverage` in dev venv: `python -m coverage --version`
- confirm `.secrets/attu-bot.toml` `[database]` section keys: `python -c "import tomlkit; d=tomlkit.load(open('.secrets/attu-bot.toml')); print(d.get('database'))"`

**dod:**
- `mongo` service added to `docker-compose.dev.yml`; `docker compose up -d mongo` starts it cleanly
- at least one component test passes from venv with no docker test container (just the mongo service)
- integration test venv behavior documented, with the config-version-staleness risk explicitly called out as pre-existing (not a new failure)
- `python -m coverage --version` succeeds in dev venv

**merge gate:** `docker compose up -d mongo` works; one component test passes from venv; service is named `mongo` with no auth/replSet exactly as mongo-cutover phase 1 expects to extend

---

### phase 1 - fix run_tests.py + fallback URL

**scope:** clean up the test runner; scope is larger than the original draft assumed.

- remove the 12-line docker auto-launch block (`if not Path('/.dockerenv').exists(): ... sys.exit(rc)`) from `scripts/run_tests.py`; the script now runs suites directly regardless of context
- remove the stale vitest docstring/comment from `extract_counts()` in `scripts/run_tests.py` (lines 26, 31)
- decide and act on `tests/python/unit/test_run_tests.py`'s three `test_vitest_*` methods (lines 78/82/86): rename to reflect what they actually test (regex generality against a vitest-shaped log line) if that's still a real case worth covering, or delete if it's dead weight - don't leave them named after a tool that's gone
- update `_read_db_config()` in `tests/conftest.py`: change final fallback from `'mongodb://mongo:27017'` to `'mongodb://localhost:27017'`

**dod:**
- `python scripts/run_tests.py` from the project root (outside docker) runs all three suites (unit, component, integration) and exits with the correct return code
- `grep '\.dockerenv\|docker compose run' scripts/run_tests.py` returns nothing
- `grep -i vitest scripts/run_tests.py` returns nothing
- no test method name references `vitest` unless it's a deliberate, correctly-named regex-generality test
- `ruff check .` clean

**merge gate:** phase 0 gate passed

---

### phase 2 - CLAUDE.md + settings + docs + skill

**scope:** update the tooling and documentation that described the old docker-only workflow.

- `CLAUDE.md` sub-agents section: change "do not run tests - never invoke `pytest`, `docker compose run ... tests`, `npm test`, or any test runner" to "do not run tests - never invoke `pytest`, `npm test`, `python scripts/run_tests.py`, or any test runner; testing is the responsibility of the main agent only"; note explicitly that the main agent runs `python scripts/run_tests.py` from the worktree
- `.claude/settings.json` (project-level, not global): `Bash(python -m pytest:*)` is already in `permissions.allow` (landed via unrelated commit `4a7d9df`) - just add `python scripts/run_tests.py` to the allow list, don't re-add pytest
- `README.md`'s "### Tests" section (currently one line, `README.md:117-120`): rewrite to cover both paths - venv workflow as primary, docker as the alternative; who-can-run-what per suite (unit: either; component: needs the `mongo` service - venv or docker; integration: needs a valid, current `.secrets/attu-bot.toml` - flag the config-version gate); **revised (phase 0 triage, 2026-08-29): docker is not a working alternative for integration tests today - the `tests` service has had no `.secrets` mount since `36f6fee` (see `bugs.md`); document docker as unit/component-only, not integration, until that gap is fixed separately**; document `ATTU_CONFIG_FILE`/`TEST_DB_URL` as the canonical db pointers - **revised (phase 0 triage, 2026-08-29): confirm which of `TEST_DB_URL` / `database.url` wins in `config.on_init()` once past the version gate before documenting either as canonical (see `bugs.md`, unresolved as of phase 0)**; document the worktree workaround: `ATTU_CONFIG_FILE=/home/jhn/Projects/doom-bot/.secrets/attu-bot.toml python scripts/run_tests.py` (or symlink `.secrets` from the main checkout) since a worktree never carries `.secrets/` on its own
- `.claude/skills/mock-compensation/SKILL.md`: replace all `doom_bot` path references with `nova_core` (description field, trigger lines, file path references, `extensions_list` reference); re-verify the `tests/python/unit/test_start_bot_loop.py:350` line reference while in there - line numbers have likely drifted since this skill was last touched

**dod:**
- `grep -r "doom_bot" .claude/skills/mock-compensation/` returns nothing
- mock-compensation's `test_start_bot_loop.py` line reference points at the right line (re-verified, not assumed)
- `grep "docker compose run.*tests\|ferret\|FerretDB" README.md` (within the Tests section) shows docker only as the documented alternative, not the sole path
- `python scripts/run_tests.py` in `.claude/settings.json` allow list
- CLAUDE.md sub-agents "do not run tests" bullet updated

**merge gate:** phase 1 gate passed; merge to trunk deferred to end of run (user instruction: no merges this run, see `log.md`)

---

## status

| phase | status |
|---|---|
| 0 - walking skeleton | pending merge |
| 1 - fix run_tests.py | pending merge |
| 2 - CLAUDE.md + settings + docs + skill | not started |
