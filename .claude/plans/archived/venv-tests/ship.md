# ship readiness — venv-tests

### blockers

none.

### resolved since original ship pass

- **[resolved, 2026-08-29]** `mongo:8` dev-compose service segfaults (exit 139): root-caused via `/bug-hunt` as two distinct bugs (host-kernel rseq incompatibility causing an idle crash; docker's default fd ulimit causing a load crash under component-test collection churn). both fixed in `dfe7a90` and empirically verified - idle survival past the prior crash point, then a full component-suite run reproducing the original load pattern with no crash. see `bugs.md`'s closed section for full detail. was `[high]` deferred at the original shipdown pass; no longer deferred.

### deferred

- [low] docker-path integration test gap: the `tests` compose service has had no way to find a config file since `36f6fee` (2026-08-02), pre-existing and unrelated to this plan; already separately surfaced to the user.
- [low] `.env`'s `ATTU_CONFIG_FILE` points at a nonexistent path; pre-existing, unrelated, already separately surfaced.
- [low] `uv.lock`/`vulture` lockfile drift; pre-existing, repo-wide, unrelated to this plan.
- [medium] cross-plan coordination, not a bug: once this plan merges, `mongo-cutover/plan.md` phase 1's scope line ("add mongo service...") should change to "extend the existing mongo service..." - deliberately left un-actioned by this plan, flagged for the user to apply at merge time.

### verdict

ship

all three phases met their own DoDs; the final whole-plan integration-check passed with every one of plan.md's 6 goals independently re-verified against the actual current files, not just log.md's word. nothing above blocks what this plan actually promised (working runner mechanics outside docker, plus documentation that's honest about the venv component path's current reliability limit rather than overselling it).

per explicit user instruction ("run it all. no merges yet"), pre-merge and the final merge are deferred past this run regardless of this "ship" verdict - this verdict says the plan is ready to merge whenever the user gives go-ahead, not that it's merging now.
