# nova-w2 bugs

## open

- **INT-BASELINE-01** integration suite: 9 pre-existing errors in baseline at phase 0 close; not introduced by phase 0 (integration check confirmed no regressions). known entries in `notes/bugs.md`: `TestBotReadyPath` failures (all envs), `nova_core.bot` re-export import path, stale discord-logging test, vestigial mock assertions. phase 2 close: 12 pass, 9 pre-existing errors unchanged - no regressions introduced by nova-w2. disposition: defer; persists beyond nova-w2 plan close; surface for integration suite maintenance as a standalone task outside nova-w2 scope.

## closed

- **NIT-W2-01** closed in 84033bf: `TZ=UTC`/`_time.tzset()` boilerplate removed from `test_feature_loader.py:10` as planned in phase 1. cosmetic; confirmed no tz-sensitive logic in the file.
