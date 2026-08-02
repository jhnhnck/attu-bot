# nova-w2 bugs

## open

- **NIT-W2-01** `test_feature_loader.py:10`: `TZ=UTC`/`_time.tzset()` boilerplate copied from sibling test files; no tz-sensitive logic in this module; remove the two lines. disposition: fix-in-phase-1; cosmetic, not a blocker. (already tracked in `notes/bugs.md` from code review; mirrored here for plan-level triage.)
- **INT-BASELINE-01** integration suite: 9 pre-existing errors in baseline at phase 0 close; not introduced by phase 0 (integration check confirmed no regressions). known entries in `notes/bugs.md`: `TestBotReadyPath` failures (all envs), `nova_core.bot` re-export import path, stale discord-logging test, vestigial mock assertions. disposition: defer; pre-existing, not blocking any w2 phase; surface for integration suite maintenance separately.

## closed
