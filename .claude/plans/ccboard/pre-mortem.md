# pre-mortem — ccboard

Adversarial review. Phases 0 and 1 predate the formal process loop — their pre-mortem was de facto, not formal. The phase-2 pre-mortem below was applied 2026-05-09 via the `pre-mortem` skill and is preserved verbatim (it remains live adversarial review of the still-open phases 2.4–2.10). The conversion & restart addendum at the bottom covers risks introduced by the 2026-06-04 format conversion and branch restart.

---

## phase 2 pre-mortem (2026-05-09)

Phase 2 splits into **2a (auditor + recount with `point_value` re-snapshot)** and **2b (user-facing `/stars` against ccboard + legacy `/stars` retirement)** per the bug-triage pattern from 2026-05-07.

**Bottom line:** **proceed with revisions** — three high-severity risks need probes before phase 2.1 starts, plus a load-bearing design decision (recount semantic) needs to be pinned before any recount code is written.

### risks

#### phase 2a (auditor + recount)

- [high] **performance** — discovery scan over channel history is unbounded by default. A guild with N text channels × M messages/channel × P reactions/message is O(N·M·P) discord API calls; py-cord's `channel.history(...)` paginates 100 per page and `reaction.users()` paginates 100 per page; even moderate guilds exhaust per-route rate limits in minutes. probe: count messages and reactions in a real attu guild over the last 30 days; compute the API call budget at 50 req/s global, 5 req/2s per route. if discovery costs >10 min per guild in best case, scope it down to "channels with recent ccboard reactions" before any code lands.
- [high] **premise** — the recount pass's `point_value` semantic is not yet pinned. `ReactionDocument.point_value` is documented as "snapshot at reaction time"; recount changes that to "snapshot at last recount". this either (a) renames the field, (b) adds `last_recounted_at`, or (c) accepts the semantic drift silently. each option has cascading impact on /debug ccboard show_reactions, leaderboard tie-breaking, and migration replay. probe: write a one-page design note answering "what does point_value mean after recount, and what do we tell users when their old votes' weights change?" — get user approval before any 2a phase 2 code.
- [high] **operational** — reconciliation diff against live discord is destructive on the wrong side. if discord returned a partial reactor list (rate-limited mid-page, or `reaction.users()` failed silently), naive "delete db reactions not seen in discord" wipes real votes. probe: write the reconcile pass with `dry_run=True` default; require an explicit `confirm=True` on `/fix ccboard recount`; surface a per-entry diff summary (added X, would-remove Y) before mutating.
- [medium] **integration** — auditor must take `ccboard.get_lock(message_id)` before mutating any entry, exactly like the watcher and manager. without it, a concurrent `handle_reaction_add` can race the recount, and `_recompute_and_mark` will overwrite recount state. mitigation: the lock dict is in-process and shared; auditor is a `BaseTask` running in the bot process; reuse `ccboard.get_lock`. low-cost; flag during code review.
- [medium] **integration** — auditor's `_safe_remove_reaction` (for orphan-cleanup or self-star repair on missed reactions) must register `_pending_bot_removals` keys *before* the api call, mirroring the watcher's pattern. without it, the echoed `on_raw_reaction_remove` corrupts point totals. mitigation: import and reuse `ccboard.register_pending_removal` / `_safe_remove_reaction` directly from the watcher rather than reimplementing.
- [medium] **dependency** — `discord.Reaction.is_burst` is read with `getattr(..., False)` in the watcher's backfill (note: spelled `is_burst` on the live reaction object, not `burst`). during reconciliation, the same defensive read is needed. on py-cord 2.7+, `is_burst` is set on the Reaction; older versions returned a tuple of normal+burst counts. mitigation: the watcher already has this pattern — copy it into the auditor verbatim, do not re-derive from raw payloads.
- [medium] **scope** — "auditor" is currently three passes (discovery, reconciliation, orphan-post). each has a different cost profile and a different correctness contract; folding them into one task obscures which pass is failing. mitigation: split into three `BaseTask` subclasses (or one task with three explicit methods) with separate `/fix ccboard` subcommands and separate logging tags. ship reconciliation first, discovery later, orphan last.
- [medium] **operational** — orphan-post cleanup (auditor scans the ccboard channel for bot-authored posts that have no `BoardEntryDocument`) is destructive on a discord-side artifact that has no DB twin. if the entry was hard-deleted by `/fix ccboard purge` while the post remained, this is correct cleanup. if the entry was lost by a botched migration, this is permanent data loss. mitigation: orphan pass also dry-run by default; add a 7-day grace period (don't delete posts younger than 7 days unless `--force`); log every deletion.
- [low] **expertise** — long-running scanners under py-cord rate limits is new for this codebase. the legacy `MessageBackfillTask` does channel history but doesn't do per-message `reaction.users()`. mitigation: add explicit `discord.HTTPException` catch with `Retry-After` honoring; cap total scan time per tick (e.g., 90s budget then yield).
- [low] **operational** — bulk `point_value` re-snapshot on recount with a ferretdb `update_many` works for one guild, but if scope ever broadens to all guilds at once, lock contention on `ccboard_reactions` could slow the watcher. mitigation: per-guild only at the command boundary; this is already the natural scope.

#### phase 2b (user-facing /stars + legacy retirement)

- [high] **integration** — two `SlashCommandGroup('stars', ...)` registrations cannot coexist in py-cord. the new ccboard-backed /stars must replace, not coexist with, the legacy starboard-backed /stars. but per-guild routing inside one command (legacy if `ccboard.enabled=False`, ccboard if `True`) requires both implementations to live in the same module. probe: prototype a one-command router (`/stars random`) that branches on guild config, verify command tree sync still works, eyeball error paths.
- [high] **premise** — the legacy `/stars` behavior post-migration is an open question. once a guild migrates via `/fix stars convert`, new reactions write only to ccboard, but legacy `/stars random` still queries the (now-frozen) legacy starboard. options: (a) hard-cutover at migration time — flip a guild flag, /stars routes to ccboard, legacy data ignored forever; (b) per-command soft-route — /stars checks `ccboard.enabled` and uses the appropriate backend. (a) is simpler but loses pre-migration visibility; (b) is more code but preserves "old data still browsable". user choice required before 2b code.
- [medium] **scope** — /stars recheck on ccboard requires a per-entry reconciliation function. that function IS phase 2a's reconciliation pass, factored to take a single message_id rather than a guild. mitigation: explicit dependency — 2a's reconciliation lands first; 2b's /stars recheck imports it.
- [medium] **integration** — ccboard /stars random/lost adds entries' response message ids to `display_message_ids` so reactions on the response redirect back to the original. the watcher's redirect resolver already handles this via `entry_repo.get_by_display_message`. but the existing legacy /stars stores a different ref (`response_doc.refs.starboard_post`) — these two redirect paths must not collide. mitigation: ccboard /stars never writes `MessageDocument.refs.starboard_post`; only writes to `BoardEntryDocument.display_message_ids`.
- [medium] **operational** — retiring legacy /stars is a destructive command-tree change. once removed, guilds that haven't migrated lose starboard browsing entirely. mitigation: keep legacy /stars in-tree but no-op routed when `ccboard.enabled=True`; full removal is a separate, much later decision.
- [low] **expertise** — none new; /stars is mostly wiring over existing repo methods (`EntryRepository.get_random`, `leaderboard_*`, `ReactionRepository.leaderboard_most_given`).

#### cross-phase

- [high] **operational** — order of operations under live use: enable ccboard → migrate via /fix stars convert → users react and post → user runs /stars and gets ccboard-backed result. if 2b ships before 2a's reconciliation, /stars recheck is missing; if 2b ships before legacy retirement is decided, /stars routing is undefined. probe: stage 2a fully (including /fix ccboard recount with re-snapshot semantic decided) before any 2b code lands.

### walking-skeleton check

The original outline's "AuditorTask registered with empty pass implementations" is a reasonable wiring-only phase 0 for **2a**, but it's not a *full* walking skeleton because it doesn't touch 2b's slash command surface. A real phase 0 for the whole of phase 2:

- `AuditorTask(BaseTask)` registered in `register_bot_tasks()`, `interval=None` (manual-trigger only), `run()` that logs "auditor stub: would-be reconcile" and returns. proves scheduler wiring without a runaway scan.
- `/fix ccboard recover` and `/fix ccboard recount` rewritten from "phase 2 only" stubs to a real call into the auditor's no-op `discover()` / `reconcile()` methods. proves the slash command → task method seam.
- `/cc stars` placeholder slash command group registered (provisional name to dodge legacy conflict), with one stub command `/cc stars test` that responds "phase 2 stub". proves the /stars surface is wireable without colliding with legacy.
- One end-to-end smoke test: enable ccboard on a test guild, invoke `/fix ccboard recount`, see the no-op log line; invoke `/cc stars test`, see the stub response. no real auditor work happens; the seams are proven.

This phase 0 retires no risk on its own, but it surfaces the *layer* problems (scheduler, slash command tree, lock dict access from auditor) before the costly probes run. Every later phase replaces a stub with real implementation; no new layer is introduced after phase 0. (Shipped as phase 2.0.)

### phase-order revisions (risk-first)

| original (placeholder)              | proposed (risk-first)                                            | reason |
|---|---|---|
| 1. AuditorTask wiring (stubs)       | 1. **walking skeleton** (auditor stubs + /cc stars stub)         | full walking skeleton covers both 2a and 2b layers; placeholder only covered 2a |
| 2. recover (discovery)              | 2. **recount design note + user approval**                       | the highest-severity premise risk is a *decision*, not code. pin the `point_value` semantic before writing any recount code |
| 3. recount (reconciliation)         | 3. **per-entry reconciliation pass (dry-run default)**           | hardest correctness; doing this before bulk discovery proves the diff logic on a controlled input |
| —                                   | 4. **per-entry recount with re-snapshot** (using approved semantic) | folds the recount semantic into the per-entry path; no bulk re-snapshot until per-entry is proven |
| —                                   | 5. **discovery pass (scoped: recently-active channels only)**    | the unbounded-scan risk is retired by scoping; full-history discovery is a later optional phase |
| —                                   | 6. **orphan-post cleanup with grace period**                     | least urgent (rare in practice); grace period bounds the destructive risk |
| —                                   | 7. **/stars random/lost on ccboard** (replaces legacy by config gate) | depends on builder + entry repo; both already exist |
| —                                   | 8. **/stars leaderboards** (most-stars, most-starred, most-given) | trivial wiring on existing repo methods |
| —                                   | 9. **/stars recheck on ccboard** (calls 2a per-entry reconcile) | depends on 2a's reconcile; explicit cross-phase dep |
| —                                   | 10. **legacy /stars routing decision** (per-guild gate vs hard cutover) | user decision; pin before any retirement |
| —                                   | 11. **legacy /stars retirement** (no-op route when ccboard.enabled, deletion deferred) | irreversible; ship last, with the option to skip |

(Mapped to plan phases 2.0 through 2.10. The per-phase definition-of-done additions produced by this pre-mortem — integration check, unknown-retired, rollback criterion — were folded into each phase's `**definition of done:**` / `**rollback:**` rows in [plan.md](plan.md), then further tightened by the phase-2.2 and phase-2.3 plan-revises recorded in [log.md](log.md).)

---

## conversion & restart addendum (2026-06-04)

Risks introduced by converting the monolithic `notes/plans/ccboard.md` into this four-file directory and restarting the branch from the `archive/ccboard-redesign` tag.

- [resolved-in-conversion] **stale branch references.** the source plan referenced `feat/ccboard-redesign` throughout (ship gate target, "13 commits ahead of dev"). the restart renamed the working branch to `feat/ccboard`. all references in [plan.md](plan.md) / [log.md](log.md) point at `feat/ccboard`; the only mention of the old name is as the archived tag.
- [open] **predecessor retirement.** source bug #11 retired the *original* gitignored `notes/plans/ccboard.md` (the architectural spec). after this conversion, the worktree's `notes/plans/ccboard.md` (the 612-line monolith) is itself the predecessor superseded by this directory. it can stay as a historical artifact or be removed at the next `pre-merge`; do not edit it further — this directory is canonical.
- [open · ship-gate] **gitignore divergence.** the `dev` worktree's `.gitignore` ignores `.claude/plans`; this worktree un-ignores it (the "force-add canonical plan; flag gitignore reconciliation" commit). on an eventual merge to `dev`/`trunk`, `.gitignore` will conflict and this plan dir would be ignored on `dev`. same class as bug #12 (environmental, deferred to ship gate). note: `pre-merge` archives the plan dir, so it need not land on `trunk` at all.
- [open · resume precondition] **resume freshness.** last project activity was 2026-05-10; this conversion is 2026-06-04. code is unchanged (checked out at the tag), but the "1346/160/13/32 green" claim is ~3.5 weeks stale — re-run `scripts/run_tests.py` to re-establish the baseline before starting phase 2.4.

**Conversion bottom line:** the open phases (2.4–2.10) and their risks are unchanged by the restart; the only new work the conversion creates is the predecessor-retirement and gitignore-reconciliation chores, both deferrable to the ship gate.
