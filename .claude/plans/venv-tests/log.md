# venv-tests - log

## extracted and audited - 2026-08-28

plan originally drafted 2026-08-15 (`cff0988`) on branch `worktree-cryptic-pondering-grove`, committed normally (`.claude/plans` is not gitignored here - only `archived/` and `wave-state.json` are excluded from casual adds) but never merged to trunk. the branch's worktree was removed at some point without merging; the branch ref itself is still present locally, just unreachable from trunk and easy to overlook. recovered via `git show cff0988:.claude/plans/venv-tests/*` into a fresh worktree (`worktree-venv-tests`, off current trunk) and audited against trunk state before any implementation.

**verification result: zero phases completed or merged.** status table's "not started" across all three phases is accurate - this is drift, not partial completion.

verified drift since the plan was written:
- `notes/` was renamed to `docs/` at some point after 2026-08-15
- `docs/dev/testing.md` (the plan's phase 2 doc target, under its post-rename name) was deliberately deleted in `49d2e88` (2026-08-24, "chore(docs): delete obsolete dev guides") along with the rest of `docs/dev/` - no replacement written; plan retargeted at README.md's "### Tests" section instead
- `.claude/settings.json` gained `Bash(python -m pytest:*)` from an unrelated commit (`4a7d9df`) - phase 2's settings.json item trimmed to just `python scripts/run_tests.py`
- the plan's claim that only a stale vitest comment needs cleanup in phase 1 was wrong - three test methods in `test_run_tests.py` are still named after vitest output shape; phase 1 scope expanded
- local `.secrets/attu-bot.toml` confirmed at `config_version = "2.6.0"` against a required `2.8.0` - phase 0's integration probe will hit this; documented in accepted risks so it isn't misattributed as a phase-0 regression
- confirmed still true / unchanged: `_PrefixedDB`/uuid4 isolation in `tests/conftest.py`; coverage source paths in `pyproject.toml`; `mock-compensation` skill's 5 `doom_bot` references; docker auto-launch block still in `scripts/run_tests.py`; conftest fallback still `mongodb://mongo:27017`; no `mongo` service in `docker-compose.dev.yml`; CLAUDE.md sub-agents wording unchanged

cross-plan: `.claude/plans/mongo-cutover/plan.md` phase 1 independently plans a `mongo` service (with auth/replSet) - same name, deliberately additive per this plan's own constraints. mongo-cutover is still all "not started" so sequencing holds. **not edited from this worktree** - flagged to the user as a pending edit to mongo-cutover once this plan lands (phase 1's scope line should change from "add mongo service" to "extend the existing mongo service").

two items found during the audit that are real but out of this plan's scope, parked in `bugs.md`: the docker-path integration test gap (`36f6fee` stripped the tests container's only path to a config file, integration tests can't run through docker at all) and `.env`'s dangling `ATTU_CONFIG_FILE` path.

plan.md revised in place to reflect all of the above. no phases marked started; nothing implemented this session.

## starting phase 0 - 2026-08-29

worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/venv-tests
branch: worktree-venv-tests (deviates from phase/<slug> convention - EnterWorktree names it, kept as-is)
parent branch: trunk
confirmed dod: mongo service added to docker-compose.dev.yml and starts cleanly; at least one component test passes from venv with no docker test container; integration test venv behavior documented (config-version staleness expected, not a new failure); coverage available in venv
run mode: auto, no merges this run (user instruction) - phases stack on this one branch, merge deferred to end
baseline: suite is already red for reasons outside this plan (2 unit failures + 14 collection errors + 11 component failures from prior stale-test commits; docker integration blocked entirely) - gates this run evaluate as "no new failures vs this baseline", not "green suite"

## phase 0 verification - 2026-08-29

all run inline by the main agent (not a subagent - CLAUDE.md forbids sub-agents from running docker/pytest):

- `docker compose -f docker-compose.dev.yml up -d mongo` - clean start, `doom-bot-dev-mongo-1` up, `0.0.0.0:27017->27017/tcp`
- component proof: `TEST_DB_URL=mongodb://localhost:27017/doombot uv run pytest tests/python/component/test_db_repositories.py::TestConfigRepositoryIndexes -m component -v` -> 2 passed, 0 docker test container involved
- integration probe: `ATTU_CONFIG_FILE=/home/jhn/Projects/doom-bot/.secrets/attu-bot.toml TEST_DB_URL=mongodb://localhost:27017/doombot uv run pytest tests/python/integration/ -v` -> 12 passed, 9 errors. all 9 errors are the exact predicted `ConfigLoadError: config file version 2.6.0 is below required 2.8.0` from accepted risks - confirmed pre-existing secrets staleness, not a new regression, not this plan's bug. `config.on_init()` reads the toml path directly for the version gate before ever touching `TEST_DB_URL`/`database.url`, so the downstream question (does it prefer `TEST_DB_URL` over the toml's `database.url` once past the gate) is still unconfirmed - the gate blocks before that code runs.
- `uv run python -m coverage --version` -> 7.13.5, present in venv
- toml `[database]` section (read from main checkout's `.secrets/attu-bot.toml` directly, worktree has none): keys are `url`, `name` - matches what `_read_db_config()` expects

phase 0 dod: met in full. mongo service added and starts cleanly; component proof passes from venv; integration behavior documented exactly as predicted; coverage confirmed.

## phase 0 retro - 2026-08-29

**what landed vs spec:** full dod met, no scope narrowing. `mongo` service added to `docker-compose.dev.yml` (`c52f4da`), component test passes from venv against it with zero docker test container, integration probe documented, coverage confirmed in venv. one accepted-risk question was deliberately left open rather than answered: whether `config.on_init()` prefers `TEST_DB_URL` over the toml's `database.url` once past the version gate - the gate rejects on `config_version` before that code path ever runs, so it's unconfirmable without either fixing local secrets or stubbing the gate, both out of phase 0's "probe, don't fix" scope.

**what surprised us:** the version-gate failure landed exactly as predicted in accepted risks - no surprise there, which is itself worth noting (the pre-mortem's direct-verification pass paid off). a pre-existing, unrelated `uv.lock`/vulture lockfile drift surfaced during verification (`f3aafc2` added the dep, lockfile never regenerated); not this plan's issue, parked in `bugs.md`. phase 1's scope had already expanded pre-execution (vitest cleanup is three test methods, not one comment) - already reflected in `plan.md`, not new this phase.

**what residual debt remains:** the `TEST_DB_URL`-vs-`database.url` precedence question - phase 2's readme rewrite plans to document `TEST_DB_URL`/`database.url` as "the canonical db pointer," which needs this confirmed first. added to `bugs.md` below.

## revision after phase 0 - 2026-08-29

bug-triage: 4 entries classified, 0 gc'd (nothing closed yet, nothing aged). new entry added for the `TEST_DB_URL`-vs-`database.url` precedence gap found during retro.

plan-revise: phase 1 - valid, no change (its scope expansion is already reflected in `plan.md` from the earlier audit; retro found nothing new). phase 2 - revise, three in-place edits to its `plan.md` section: (1) readme bullet now notes the docker-path integration gap (`bugs.md`) so it isn't documented as a working alternative, (2) readme bullet now requires confirming `TEST_DB_URL` vs `database.url` precedence before calling either "canonical", (3) merge gate changed from "phase 1 merged to trunk" (contradicts this run's no-merge instruction) to "phase 1 gate passed; merge to trunk deferred to end of run (user instruction, see log.md)".

status table: phase 0 flipped from "in progress" to "closed in b1f8998".

## status correction - 2026-08-29

phase-close set phase 0's status to `closed in b1f8998` - corrected to `pending merge`. `closed in <sha>` specifically means merged to trunk (plan-manager reference.md's status table); no merge happened this run per explicit user instruction ("run it all. no merges yet"). all phases in this run end at `pending merge`, collapsing into one eventual ff-merge once the user gives go-ahead.

## starting phase 1 - 2026-08-29

worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/venv-tests (unchanged, reused)
branch: worktree-venv-tests
parent branch: trunk
confirmed dod: run_tests.py runs all three suites directly outside docker and exits with correct code; no .dockerenv/docker-compose-run references remain; no test method name still says vitest unless deliberately kept and correctly named; ruff check clean (no new issues vs baseline)
scope confirmed unchanged from plan.md's phase 1 section (already revised pre-execution: vitest cleanup scope expanded beyond one comment, per audit).

## phase 1 verification - 2026-08-29

all run inline by the main agent (not a subagent):

- grep checks: `grep '\.dockerenv\|docker compose run' scripts/run_tests.py` -> clean; `grep -i vitest scripts/run_tests.py tests/python/unit/test_run_tests.py` -> clean
- `uv run ruff check .` -> 13 errors, same count and same files as the pre-existing baseline established at session start (S105/RUF103 in test_wiki_http.py etc.) - no new issues from this phase's changes
- full run: `uv run python scripts/run_tests.py` (outside docker, ATTU_CONFIG_FILE pointed at main checkout's secrets, TEST_DB_URL at local mongo) -> real exit code confirmed `1` (captured properly this time, not masked by a tail pipe) - correct: the runner exits 1 because suites failed, matching its own `sys.exit(1)` logic. mechanical dod item ("runs all three suites directly, no docker relaunch, exits with the correct return code") is fully met.
- unit: 3 failed, 1191 passed, 14 errors - matches the known local-without-DEBUG baseline exactly (2 pre-existing regressions + 1 DEBUG-env-dependent test that only passes with DEBUG=1 set, not a new issue)
- integration: 12 passed, 9 errors - identical to phase 0's probe, the same pre-documented config-version-staleness error, nothing new
- component: two full runs both hit a reproducible `mongo:8` container segfault (exit 139) partway through the suite - not this phase's regression, not caused by phase 1's code changes (phase 0's own service). logged as an in-scope bug needing a decision in bugs.md. mongo restarted and confirmed reachable again after each crash; small-scope component runs (a handful of tests) pass cleanly.

phase 1 dod: met on its own mechanical terms (runner behavior, vitest cleanup, fallback URL, ruff clean). full green suite remains out of reach - for the same pre-existing reasons as phase 0 (unit/integration) plus a newly-discovered container reliability issue (component) that's now logged for a decision, not silently absorbed.
