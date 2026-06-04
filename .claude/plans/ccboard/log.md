# log — ccboard

Phase retros + `plan-revise` what-changed summaries + the ship gate, chronological, append-only. The triaged bug dispositions referenced below live in [bugs.md](bugs.md).

---

## phase log (retrospective)

### phase 0 (de facto: foundation slice F)

Walking-skeleton equivalent. Documents, repositories, db wiring, and ccboard package init. No behavior — just the data layer through which every later slice talks.

- `ReactionDocument`, `BoardEntryDocument` in `attu_models`
- `ReactionRepository`, `EntryRepository` with full CRUD + leaderboard aggregations
- `apps/bot/doom_bot/database/__init__.py` — instantiation + wiring of the new repos
- `apps/bot/doom_bot/ccboard/__init__.py` — per-message lock dict, `_pending_bot_removals` echo-suppression set, helper functions

Verified with the existing test suite (1438 tests). No behavior, no new tests.

### phase 1 (parallel slices, three waves)

Wave 1 — single agent, sequential. Slice F (foundation, above).

Wave 2 — three slices, sub-agent worktrees where possible:
- **Slice C (config)** — main agent. Tier-3 plumbing for `GuildCCBoard`. Caught the `save_guild` silent-default bug via the new roundtrip test.
- **Slice B (builder)** — sub-agent. Pure rule-pipeline embed builder, 10 rules, multi-image gallery fix.
- **Slice M (migration)** — main agent (sub-agent's worktree got a stale base twice). `/fix stars convert` with idempotent semantics and bot-reply attribution.

Wave 3 — two parallel slices + one integration step:
- **Slice W (watcher)** — sub-agent. Four raw reaction handlers; redirect / backfill / one-vote enforcement / echo suppression. Edits `events.py` additively, gated on `ccboard.enabled`.
- **Slice T (manager)** — sub-agent. `ManagerTask` 10s poll, 60s settle debounce, `_sync_post` with all five branches, sweep streak counter.
- **Slice I (integration)** — main agent. `/fix ccboard {regen, purge, recover-stub, recount-stub}`, `/debug ccboard show_reactions`, `notes/features/ccboard.md`, `notes/agents.md` update, `notes/to-do.md` ccboard section.

Final state: 1501 tests pass; behavior matches spec; no push, no deploy.

---

## ship readiness — ccboard phase 1 (2026-05-07)

Applied via the `ship-readiness` skill. The cut-line below was the gate for merging the ccboard branch → `dev`. (Branch was `feat/ccboard-redesign` at the time; it is `feat/ccboard` after the 2026-06-04 restart.)

### prerequisites
- [x] **integration-check** — full test suite passed at HEAD (`98f7cc3a`): 1302 unit + 154 component + 13 integration + 32 JS = 1501 tests, 0 failures
- [x] **feature-completion** — slice I closed with tests, documentation, configuration plumbing (six-step tier-3), web interface, and lint all clean
- [x] **code-review** — no uncommitted changes other than the intentional `.secrets` symlink and the plan file itself

### blockers
- **env: dev-tree merge conflict** — `/srv/services/doom-bot-dev` has uncommitted WIP on `events.py` (291 lines), `modlog.py`, `starboard.py`, `util.py`, `logging.py`, `scheduler.py`, `wiki/client.py`, `webhook.py`, `commands/trees.py`, `tests/conftest.py`, `notes/agents.md`, `notes/to-do.md`, and `uv.lock`. Slice W's edits to `events.py` will conflict on merge. Until the user commits, stashes, or rebases this WIP, the merge to `dev` is unsafe (bug #12) · 30 min – 2 hours.

### verdict
**Project boundary deferred until feature-complete (post phase 2).** Per user direction 2026-05-07: ccboard stays on its branch and accumulates phase 2 work on the same branch. The dev merge is not the next milestone — feature completion is. Item #12 is not a current blocker because no merge is pending; it gets re-walked when ship-readiness next runs (after phase 2). Deferred follow-ups (#5, #6, #7, #8, #9, #10) are tracked in [bugs.md](bugs.md).

---

## phase 2.2 retro — 2026-05-10

Applied via the `phase-retro` skill against commit `133e96f5`.

### spec delta
- delivered: per-entry reconcile via `reconcile_entry(guild_id, message_id, dry_run=True)` plus `/fix ccboard recount <link> [confirm]`. pure `_compute_diff` (seven outcome buckets: add / replace / remove / matching / strip_invalid / strip_extras / partial flag), `_apply_diff` apply path, lock cooperation via `ccboard.get_lock(message_id)`, partial-pagination degradation, watcher's `_safe_remove_reaction` reused for self/bot/extras stripping. unit + component tests cover dry-run, apply, partial, no-change, missing entry, disabled cfg, unfetchable message, invalid-link, cross-guild rejection.
- missed / deferred:
  - **DoD integration check #3 (lock cooperation under live watcher activity) — not exercised.** lock pattern is inspectionally identical to the watcher's, but no test runs `handle_reaction_add` concurrently with `reconcile_entry` to prove the per-message lock serializes them. → bug #13.
- extra (beyond DoD):
  - **apply path landed** — DoD specified dry-run only; apply was added opportunistically with a `confirm=True` gate. diffs were sane, but the dry-run-only rollback criterion could not have fired since `dry_run=False` paths bypass it.
  - one-vote-per-message enforcement (`to_strip_extras`) added to the diff. the watcher already enforces this on event handling; reconcile now mirrors it.
  - duplicate `aggregate_points` call in the apply path caught and fixed pre-commit.

### surprises
- assumption: dry-run cautious path, apply lands later → reality: apply wired the same session under a `confirm=True` gate → delta: phase 2.2 collapsed 2.2 and a would-be 2.2b; phase 2.3 inherits a working apply-path scaffold.
- assumption: `_compute_diff` a flat add/remove pair → reality: grew to seven discrete buckets to handle one-vote enforcement, self/bot stripping, partial degradation in one structured pass → delta: recount becomes "another bucket fed from the staleness predicate" rather than a parallel codepath.
- assumption: `partial=True` only from a single-emoji failure → reality: `_collect_live_reactions` raises `partial=True` on any per-emoji `reaction.users()` failure OR mid-stream pagination loss; `_compute_diff` then suppresses **all** removes globally → delta: more conservative than the mitigation called for; a single flaky emoji blocks every soft-delete on the entry (bug #16).
- assumption: unit harness could exercise component flows with monkeypatches → reality: bare `pytest tests/python/component/...` hits `ServerSelectionTimeoutError` on `ferret:27017`; component tests must go through `scripts/run_tests.py` → delta: workflow gotcha, now a documented constraint.
- duplicate `aggregate_points` call made it into the working tree before commit; caught by inspection, not tests (both calls returned the same value) → delta: structural review beats test review for "calls happen exactly once".

### residual debt
- watcher↔auditor concurrent-write integration not proven by test → bug #13.
- `reconcile_guild` still a stub; `/fix ccboard recount` without `<link>` falls through to it → phase 2.4 absorbs (part of bug #6).
- `_apply_diff` ignores `_safe_remove_reaction` return values → bug #14.
- partial-pagination degradation has unit coverage only → bug #15.
- single-flaky-emoji blocks all soft-deletes on an entry → bug #16.

### triage 2026-05-10 (phase 2.2)
Dispositions recorded in [bugs.md](bugs.md). Pattern: #13/#14/#15/#16 share one root — the auditor's apply path landed without a real-discord integration check. Not a phase-level rewrite; a phase-2-ship-gate signal → added the live-discord smoke-check section to the ship gate (below). #6 is now structurally split across 2.2 (per-entry, done) and 2.4 (guild-wide). #9 narrowed: 2.2's replace bucket already carries recount's mutation shape.

---

## revision after phase 2.2 — 2026-05-10

Applied via the `plan-revise` skill against the phase 2.2 retro and 2026-05-10 triage.

what changed:
- phase 2.3 (per-entry recount): **revise** — scope narrowed to fold into 2.2's `_compute_diff` via a `to_recount` bucket fed by the staleness predicate; data-model + watcher-stamp + web-save-bump items spelled out; rollback tightened to "recount changed `point_value` for a record the predicate didn't match".
- phase 2.4 (discovery, scoped): **revise** — absorbs the still-stub `reconcile_guild` (the no-link path of `/fix ccboard recount`); guild-wide reconcile is now half of 2.4 alongside scoped discovery; closes the remaining half of #6.
- phases 0, 1, 2.0–2.2: complete. phases 2.5–2.10: valid — no premise shifted.

new section added: **phase 2 ship gate** (below) — captures the live-discord smoke checks clustered under #13/#14/#15/#16. one ship-gate checklist, not four code patches.

---

## phase 2.3 retro — 2026-05-10

Applied via the `phase-retro` skill against commit `199a703c`.

### spec delta
- delivered: phase 2.3's seven scope items (a)–(g) all landed. `ReactionDocument.last_recounted_at` added; `GuildCCBoard.weights_updated_at` added (flows through `GuildConfigDocument.ccboard` automatically since it is `dict[str, Any]`); both web save paths bump `weights_updated_at` only when `emojis` or `super_bonus` actually change; watcher's same-emoji refresh stamps `last_recounted_at = now` and re-snapshots `point_value` from current cfg; `_compute_diff` grew a `to_recount` bucket (gated by the standalone `_is_stale` predicate); `_apply_diff` runs soft-delete + upsert with fresh `point_value` and stamped `last_recounted_at`; `recount_entry` is a thin wrapper retagging `kind='recount_entry'` on `reconcile_entry`'s result. summary line gained `recount=N`. 17 new tests; full sweep 1346/160/13/32 green.
- missed / deferred:
  - per-record `point_value` before/after delta logging — missed; apply path logs only the aggregate `recount=N` line → bug #17.
  - `/debug ccboard show_reactions` does not display `last_recounted_at` → bug #18.
- extra (beyond DoD):
  - web save bump applied to **two** routes (`PATCH /api/guilds/<id>/ccboard` and the whole-config endpoint), not one; second caught by inspection.
  - `_classify_existing_match` helper extracted to keep `_compute_diff` under the `PLR0912` 12-branch ceiling.
  - `_is_stale` shipped as a standalone, separately-tested helper; five direct tests pin its behavior.

### surprises
- assumption: extending `_compute_diff` a one-line addition → reality: hit the `PLR0912` 12-branch limit, extracted `_classify_existing_match` → delta: every future bucket hits the same wall (bug #19).
- assumption: bumping `weights_updated_at` a one-liner → reality: two routes, both lose the field on roundtrip without explicit preserve logic since the form omits it → delta: any future user-hidden tier-3 field needs the same preserve-and-bump dance (bug #20).
- assumption: `recount_entry` would need its own apply path → reality: `_apply_diff`'s replace bucket already did "soft-delete old + upsert fresh point_value"; recount-as-bucket was ~20 lines → delta: 2.2's bucket-shaped choice paid off as predicted.
- assumption: tightened rollback hard to test → reality: `test_recount_skipped_when_last_recounted_after_bump` + `test_uses_last_recounted_at_when_set` prove the predicate refuses non-stale records — the inverse of the rollback condition → delta: rollback proven by structural invariant.
- pre-existing import-sort lint error in `tests/python/unit/test_run_tests.py` surfaced again (bug #21); not 2.3 work, but `ruff check` flags it repo-wide.

### residual debt
- per-record `point_value` delta logging missing → bug #17.
- `/debug ccboard show_reactions` should display `last_recounted_at` → bug #18.
- `_compute_diff` at the `PLR0912` ceiling → bug #19.
- web save bump logic duplicated → bug #20.
- pre-existing import-sort error in `test_run_tests.py` → bug #21.

### triage 2026-05-10 (phase 2.3)
Dispositions in [bugs.md](bugs.md). Patterns: #17/#18 are diagnostic gaps from 2.3 prioritizing correctness over observability (#18 → 2.4 scope, #17 rides as a patch follow-up). #19/#20 are code-health debt with natural homes (2.5 / third-occurrence). #9 now mostly delivered — guild-wide bulk recount falls into 2.4's `reconcile_guild` iteration for free.

---

## revision after phase 2.3 — 2026-05-10

Applied via the `plan-revise` skill against the phase 2.3 retro and triage.

what changed:
- phase 2.4 (discovery, scoped + guild-wide reconcile + recount): **revise** — (i) recount inherited free since per-entry iteration calls `reconcile_entry` which honors `cfg.weights_updated_at`; (ii) absorbs #18 (extend `show_reactions` to render `last_recounted_at`); (iii) rollback gets a second trigger mirroring 2.3's — abort if guild-wide recount mutates `point_value` for a non-stale record.
- phase 2.5 (orphan-post cleanup): **revise** — adds an implementation note for #19: if orphan signals fold into `_compute_diff`, extract another `_classify_*` helper or `# noqa: PLR0912 — <reason>`; silently bumping the lint limit is not acceptable.
- phases 2.6–2.10: valid — 2.3 didn't touch the user-facing /stars or legacy-retirement design.

bug-log items the revision retired or moved: #6 now 2.4-only (per-entry done in 2.2+2.3); #9 per-entry delivered in 2.3, guild-wide absorbed into 2.4; #18 folded into 2.4 DoD; #19 folded into 2.5 note. #17, #20, #21 deferred, not load-bearing.

---

## phase 2 ship gate

Created 2026-05-10 alongside the phase 2.2 plan-revise. This is the pre-merge gate for `feat/ccboard` → `dev` after **all** of phase 2 (2.3 through 2.5 at minimum; 2.6+ may ship in a separate gate per the 2a/2b split). Mechanical checks (ruff / basedpyright / `scripts/run_tests.py` green) are a precondition, not part of this gate.

### live discord smoke checks
Cover the bug-log items unit/component tests cannot exercise (#13–#16). Each is a manual check against a real guild with `ccboard.enabled=True`.

1. **Watcher↔auditor concurrent lock cooperation (#13).** Add a real reaction to a tracked message **while** `/fix ccboard recount <link> confirm:True` runs on that same message. Expected: no duplicate `ReactionDocument`, no missed soft-delete, no point-aggregate corruption. Failure: a `KeyError` or phantom reaction surviving the next manager tick.
2. **`_safe_remove_reaction` failure path (#14).** Force a `discord.HTTPException` from `message.remove_reaction` (revoke `Manage Messages` mid-recount, or rate-limit). Expected: the diff summary still reports `strip_invalid=N`/`strip_extras=N`, the reaction stays put, `_pending_bot_removals` left clean. Failure: a stuck pending key eats the next remove echo silently.
3. **Real flaky pagination (#15).** Run `/fix ccboard recount <link>` against a message with >200 of one emoji while near the global rate limit. Expected: any pagination failure surfaces `partial=True` and the apply path skips removes; never a "would remove every reaction" diff. Failure: a partial silently treated as complete soft-deletes real reactions.
4. **Per-emoji partial isolation (#16).** Reproduce a partial-mode reconcile; verify via the log that **all** removes are suppressed, not just the failing emoji's. This confirms the conservative behavior shipped. Failure: removes for healthy emojis applied during a partial run breaks the invariant; #16 needs redesign before merge.

### other gates (carry-forward from phase 1)
- `integration-check` against the running watcher/manager/auditor stack
- `bug-triage` re-walk of the open log (re-evaluate #8, #13–#16; at least #13 should leave the log resolved)
- dev-tree merge conflict (#12) re-walked here per the 2026-05-07 verdict
- final `code-review` over the cumulative phase-2 diff
- `feature-completion` checklist clean across the whole phase

### verdict format (filled at gate time)
| ship-or-no? | rationale |
|---|---|
| _(filled by `ship-readiness` at the gate)_ | _(blockers, deferred items, follow-ups)_ |

---

## starting phase 2.4 — 2026-06-04

Working in existing worktree `.claude/worktrees/ccboard`, branch `feat/ccboard` (per user instruction: same worktree, no new phase branch).

**Confirmed DoD:**
- discovery on one channel completes within a 90s time budget (rate-limit waits logged, never unbounded)
- no `ReactionDocument` created without a `BoardEntryDocument`
- guild-wide reconcile produces the same per-entry diffs as running `/fix ccboard recount <link>` per entry
- post-`weights_updated_at`-bump, guild-wide recount re-snapshots every stale active record and leaves fresh ones untouched
- `/debug ccboard show_reactions` renders `last_recounted_at` (closes #18)

---

## phase 2.4 retro — 2026-06-04

### spec delta
- delivered: all five DoD items. `reconcile_guild` iterates every `BoardEntryDocument` per-guild under a 90s budget (recount free via staleness predicate). `discover_guild` scans channel history bounded to channels with existing entries. `/debug ccboard show_reactions` renders `last_recounted_at`. `/fix ccboard recount` (no-link path) is real.
- missed / deferred: none
- extra: `distinct_channel_ids(guild_id)` added to `EntryRepository` (required by discover_guild scope derivation — not in DoD but obviously load-bearing). Discord 100-char command description limit hit during integration check; shortened from 110 → 87 chars.

### surprises
- assumption: "watcher's recent-reactions channel set" implied an in-memory tracking structure → reality: the watcher doesn't maintain one; distinct `channel_id` from existing entries is the natural scope derivation → delta: added a `distinct_channel_ids` repo method; scoping is arguably more correct (only channels we know had ccboard activity)
- assumption: `isinstance(channel, discord.abc.Messageable)` would pass for `MagicMock` → reality: mock objects don't satisfy ABC `__instancecheck__`; needed a real `_FakeChannel(discord.abc.Messageable)` subclass → delta: test is more correct and exercises the real isinstance gate
- assumption: updating the `/fix ccboard recount` command description string was cosmetic → reality: Discord enforces a 100-char hard limit on option/command descriptions; the new description was 110 chars and failed extension import validation → delta: caught by `TestExtensionImports` during integration check and fixed before step 3 closed

### residual debt
- pre-existing: #14 (`_apply_diff` ignores `_safe_remove_reaction` return values) · unchanged, still deferred
- pre-existing: #17 (per-record `point_value` delta logging missing) · unchanged, still deferred

### implications for downstream phases
- phase 2.5 (orphan cleanup): no premise change; `_compute_diff` branch ceiling note (#19) is still the implementation constraint to watch if orphan signals fold into the diff
- the test pattern for `_FakeChannel` is reusable if later phases add more channel-walking logic in the auditor

---

## revision after phase 2.4 — 2026-06-04

- phase 2.5 (orphan cleanup): **valid** — `← NEXT` marker moved here; no premise change
- phases 2.6–2.10 (/stars surface + legacy retirement): **valid** — no premise change from 2.4

---

## conversion to four-file format — 2026-06-04

Restarted the project: tagged the discarded `feat/ccboard-redesign` history as `archive/ccboard-redesign` (`f6483dd8`, phases 0–2.3), deleted the old worktree+branch, and created a fresh worktree at `.claude/worktrees/ccboard` on branch `feat/ccboard` checked out from that tag — all code preserved.

Converted the 612-line monolith `notes/plans/ccboard.md` into this four-file directory per `notes/dev/process.md`: forward-looking spec + phase status → [plan.md](plan.md); phase-2 pre-mortem + new conversion addendum → [pre-mortem.md](pre-mortem.md); phase log, retros, revisions, ship gate (this file) → log.md; bug log + triage dispositions → [bugs.md](bugs.md). Phase numbering (0, 1, 2.0–2.10) preserved for cross-reference; phases 0–2.3 marked closed, 2.4–2.10 open. Branch references updated `feat/ccboard-redesign` → `feat/ccboard`. No code changed. The monolithic `notes/plans/ccboard.md` is now a superseded predecessor (see the conversion addendum in [pre-mortem.md](pre-mortem.md)); retire it at `pre-merge`. Resume precondition: re-run `scripts/run_tests.py` to refresh the ~3.5-week-stale 1346/160/13/32 baseline before starting phase 2.4.
