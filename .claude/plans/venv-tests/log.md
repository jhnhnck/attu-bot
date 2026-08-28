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
