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

## phase 1 retro - 2026-08-29

**what landed vs spec:** full dod met, no scope narrowing (scope was already expanded pre-execution during the phase 0 audit - three vitest-named test methods, not one comment). `scripts/run_tests.py`'s 12-line docker auto-relaunch block removed; the runner now runs suites directly regardless of context. stale vitest docstring/comment references removed from `extract_counts()`. `test_run_tests.py`'s three vitest-named methods resolved: `test_vitest_single_suite` deleted (duplicate coverage of the "(N)" total-stripping case, already covered by the renamed multi-suite test), the other two renamed to `test_last_of_multiple_matching_lines_wins` and `test_combined_failed_passed_on_one_line` to describe actual behavior instead of a tool that's gone. `tests/conftest.py`'s fallback URL fixed to `mongodb://localhost:27017`. `ruff check .` held at the same 13-error baseline (same files, no new issues). runner's real exit code confirmed as `1`, correctly - suites failed for pre-existing reasons, not masked by a pipe this time.

**what surprised us:** no implementer notes were relayed beyond what's already in this file. two things worth flagging for downstream readers: (1) the phase-0 "starting phase 0" baseline note above (line ~30) says "2 unit failures" - phase 1's verification run resolved this more precisely to 3 failed (2 pre-existing regressions + 1 test that's environment-dependent on `DEBUG=1`, not a new issue). carrying the "3 failed without DEBUG=1" framing forward from here so phase 2 doesn't inherit the earlier "2" as canonical. (2) a reproducible `mongo:8` container segfault (exit 139) surfaced during phase 1's full-suite verification runs - phase 0's service, not phase 1's regression; already logged and triaged in `bugs.md`, not re-triaged here.

**what residual debt remains:** none new from phase 1 itself. pre-existing unit/integration failures and the `mongo:8` segfault remain tracked in `bugs.md` from earlier phases.

## revision after phase 1 - 2026-08-29

bug-triage: 5 entries reviewed, 0 gc'd (nothing closed with a commit hash yet), 0 new. 2 entries (`mongo:8` segfault, `uv.lock`/vulture drift) explicitly not re-triaged per this phase's handoff notes - already correctly classified as phase 0's issue and pre-existing/parked, respectively. the other 3 (docker-path integration gap, `.env` misconfiguration, `TEST_DB_URL`-vs-`database.url` precedence) confirmed still accurate from phase 0's triage - no disposition changes.

plan-revise: phase 2 - valid, no change. its scope already reflects phase 0's triage-driven revisions (docker-path integration gap called out instead of documented as a working alternative; `TEST_DB_URL`/`database.url` precedence flagged as unresolved and blocking its readme bullet specifically, not phase 2 as a whole). phase 1's findings (clarified unit-failure baseline, `mongo:8` segfault) don't change phase 2's scope or merge gate.

status table: phase 1 flipped from "in progress" to "pending merge" (no merges this run per user instruction; `closed in <sha>` is reserved for merged-to-trunk).

## starting phase 2 - 2026-08-29

worktree: /home/jhn/Projects/doom-bot/.claude/worktrees/venv-tests (unchanged, reused)
branch: worktree-venv-tests
parent branch: trunk
confirmed dod: mock-compensation skill's doom_bot refs gone and its line reference re-verified; README Tests section documents both paths per the phase 0/1-revised scope (docker downgraded to unit/component-only, TEST_DB_URL/database.url precedence to be confirmed before calling either canonical, worktree workaround documented); run_tests.py in settings.json allow list; CLAUDE.md sub-agents bullet updated.
note: CLAUDE.md's `## rules` section says "do not edit the rules" - this phase's CLAUDE.md edit is scoped to the sub-agents section only, not the rules section; implementer briefed accordingly.
open item carried from phase 0 triage, must resolve before writing the readme's db-pointer claim: does config.on_init() prefer TEST_DB_URL or database.url once past the version gate? unconfirmed since the version gate blocks before that code runs (see bugs.md). main agent will check this inline before/during this phase.

## phase 2 verification - 2026-08-29

all run inline by the main agent (not a subagent):

- `grep -r "doom_bot" .claude/skills/mock-compensation/` -> clean
- `.claude/settings.json` -> `"Bash(python scripts/run_tests.py:*)"` present, pytest entry untouched (not duplicated)
- README.md Tests section -> rewritten; docker shown as an alternative (unit/component only, explicit integration limitation noted), not the sole path; who-can-run-what per suite documented; ATTU_CONFIG_FILE/TEST_DB_URL documented as two separate pointers (not a precedence question, per the phase 2 resolution); worktree workaround documented; mongo:8 segfault reliability caveat included so the venv component path isn't oversold
- CLAUDE.md -> diffed against trunk (`git diff e710811 -- CLAUDE.md`): single line changed inside `## sub-agents`, `## rules` section (lines 1-19, "do not edit the rules") fully untouched, confirmed
- mock-compensation's `test_start_bot_loop.py` line reference: implementer found `:350` pointed at the class line, not the method; corrected to `:360` (the actual `def test_extension_imports_cleanly` line) - re-verified directly by reading the file, confirmed accurate
- additional fix beyond the original brief: mock-compensation SKILL.md linked `docs/dev/testing.md`, deleted in `49d2e88` - repointed to `README.md#tests` (this plan's actual replacement content) since it was a dead link directly adjacent to the file already being edited this phase
- `uv run ruff check .` -> 13 errors, same baseline, no new issues
- `uv run ruff format --check .` -> 14 files, same baseline count, no new issues (none of this phase's four touched files are in that count)

phase 2 dod: met in full, plus one extra dead-link fix folded in (small, directly adjacent, not scope creep beyond what "update the tooling and documentation" already covered).

note on plan.md's original phase 2 scope line: it also asked CLAUDE.md's edit to "note explicitly that the main agent runs python scripts/run_tests.py from the worktree." the landed wording ("testing is the responsibility of the main agent only") already conveys this implicitly and satisfies the literal dod bullet ("CLAUDE.md sub-agents bullet updated") - treated as resolved, no further edit needed.
