# ship readiness — venv-tests

### blockers

none.

### deferred

- [high] `mongo:8` dev-compose service segfaults (exit 139) on a full local component-suite run, reproduced twice; short/small runs are unaffected. new-feature reliability gap, not a regression of prior working functionality (docker's own path never hit this - it runs FerretDB, not real mongod). already honestly disclosed in `README.md`'s Tests section rather than papered over. needs a user decision: try `mongo:7`, check for a known `mongo:8` issue, or accept short-run-only reliability. root-causing a mongod segfault is outside this plan's scope.
- [low] docker-path integration test gap: the `tests` compose service has had no way to find a config file since `36f6fee` (2026-08-02), pre-existing and unrelated to this plan; already separately surfaced to the user.
- [low] `.env`'s `ATTU_CONFIG_FILE` points at a nonexistent path; pre-existing, unrelated, already separately surfaced.
- [low] `uv.lock`/`vulture` lockfile drift; pre-existing, repo-wide, unrelated to this plan.
- [medium] cross-plan coordination, not a bug: once this plan merges, `mongo-cutover/plan.md` phase 1's scope line ("add mongo service...") should change to "extend the existing mongo service..." - deliberately left un-actioned by this plan, flagged for the user to apply at merge time.

### verdict

ship

all three phases met their own DoDs; the final whole-plan integration-check passed with every one of plan.md's 6 goals independently re-verified against the actual current files, not just log.md's word. nothing above blocks what this plan actually promised (working runner mechanics outside docker, plus documentation that's honest about the venv component path's current reliability limit rather than overselling it).

per explicit user instruction ("run it all. no merges yet"), pre-merge and the final merge are deferred past this run regardless of this "ship" verdict - this verdict says the plan is ready to merge whenever the user gives go-ahead, not that it's merging now.
