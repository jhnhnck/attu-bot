# ship readiness — ccboard (feat/ccboard)

gate run: 2026-06-05 · all phases 0–2.10 + ccboard-cutover phases 0–2 closed

## prerequisites

- integration-check: ✅ 1384 unit / 180 component / 13 integration / 32 JS — all passing
- feature-completion:
  - tests: ✅ full suite green; all new config fields have roundtrip tests; TestExtensionImports passes
  - ruff check: 5 pre-existing errors (bug #21 `tests/python/unit/test_run_tests.py` import-sort; 4 in `scripts/coverage_report.py`) — not ccboard code
  - ruff format: ✅ clean
  - js lint: 3293 pre-existing errors (eslint scanning `.venv` vendor JS; no ccboard-specific errors)
  - docs: `notes/features/ccboard.md` ✅; `notes/dev/ccboard-migration.md` ✅
  - to-do.md ccboard section stale (2.6–2.10 not reflected) — pre-merge cleanup
- code-review on uncommitted: ✅ working tree clean (only `.secrets` untracked, correct)
- basedpyright: 22 errors — 8 pre-existing in `doom_bot/logging.py`; 9 pre-existing missing-import in `attu_chat/ingestor/` (optional deps); 4 `_FakeChannel` method-override errors in test harness (tests pass; fundamental limitation of ABC mock)

## blockers

none

## deferred

- [high] #12 — dev-tree merge conflict: `dev` branch has uncommitted WIP in `events.py` (291 lines) + `modlog.py`, `starboard.py`, `util.py`, `logging.py`, `scheduler.py`, `wiki/client.py`, `webhook.py`, `commands/trees.py`, `tests/conftest.py`, `notes/agents.md`, `notes/to-do.md`, `uv.lock`. ccboard also edits `events.py` — manual conflict resolution required before merge. commit or set aside dev WIP before running `git merge feat/ccboard`.
- [high] #13 — watcher↔auditor concurrent lock cooperation not verified on real Discord. code is inspectionally correct (both paths take `ccboard.get_lock(message_id)` asyncio lock); planned live smoke check not run (Discord interaction requires explicit user instruction). recommend running the smoke check (log.md ship gate, item 1) before enabling on any production guild.
- [medium] #8 — `effective_author_id` re-resolution: once set or left None during backfill, never revisited. explicit non-goal; revisit before enabling on guilds with significant wiki attribution.
- [low] #14 — `_apply_diff` ignores `_safe_remove_reaction` return values; strip-count operator metric may undercount on discord remove failure. no data impact.
- [low] #15 — partial-pagination degradation verified by unit tests only; real-Discord flaky stream path not smoke-tested. defensive by design (partial=True → suppress all removes).
- [low] #16 — single flaky emoji blocks all soft-deletes (per-entry, not per-emoji). accepted conservative behavior; sharpen to per-emoji flags later if production shows it bites.
- [low] #17 — per-record `point_value` before/after delta logging missing; `_apply_diff` logs only aggregate `recount=N`. land as a standalone debug-log patch anytime.
- [low] #20 — `weights_updated_at` preserve-or-bump block duplicated across two web endpoints. extract a helper if a third user-hidden field needs the same dance.
- [low] #21 — pre-existing import-sort error in `tests/python/unit/test_run_tests.py`. auto-fixable via `ruff check --fix`; land as standalone `chore: ruff` commit.
- [low] #7 — wiki-attribution pass (parse webhook author → discord id via `wiki_identities`). explicit non-goal; revisit after usage data.
- [low] #10 — extension reload policy (per-call gating vs `reload_extension()` on toggle). current approach works; revisit only if slash-command visibility becomes a problem.

## deferred home

all items above migrate to `notes/to-do.md` (polish/design/future) or `notes/bugs.md` (defects) during pre-merge.

## verdict

**ship**

no blockers. all phases delivered. tests pass. code correct. deferred items have clear homes and severity tags. #12 (merge conflict) and #13 (smoke check gap) are the two high-severity follow-ups — both addressed by pre-merge process steps and a smoke check before any guild enables ccboard.
