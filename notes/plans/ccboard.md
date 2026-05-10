# ccboard — replacement reaction board

Tracking plan for the ccboard project. Phase 1 has shipped on `feat/ccboard-redesign` (13 commits ahead of `dev`). Phase 2 (auditor + user-facing `/stars` against ccboard) is the next milestone and runs through the full process loop in `notes/dev/process.md`.

This file is the canonical project plan. The architectural spec that drove phase 1 lived briefly at `notes/plans/ccboard.md` outside git history; it has been superseded by this file and the finalized reference at [notes/features/ccboard.md](../features/ccboard.md).

---

## goals

Small, co-equal, measurable.

1. **Replace the legacy starboard with a configurable signed-emoji board.** Per-guild `ccboard.emojis` is a `dict[str, int]`; positive weights count toward threshold, negative weights reduce `net_points` but never block posting on their own.
2. **Per-message reaction state survives missed events** — same-emoji re-react self-heals via in-place refresh. Aggregate gaps are recovered by the phase 2 auditor.
3. **Bot-attributable messages credit the originating user via `effective_author_id`.** Self-star check, leaderboards, and sweeps all credit the resolved author, not the bot.
4. **Migration is opt-in and idempotent.** `/fix stars convert` requires `confirm=True` and a non-empty `ccboard.emojis`; re-running yields the same final state.
5. **Phase 1 ships behind a default-off feature flag.** No behavior change to the legacy starboard until a guild flips `enabled`.
6. **All existing tests still pass after merge.** Phase 1 ships at 1501 tests across unit / component / integration / JS suites.

---

## process

This project predates the new `notes/dev/process.md` loop and was course-corrected onto it after phase 1 shipped. Phase 1's process artifacts (pre-mortem, formal phase retros, formal `integration-check`) are de facto, not formal. Phase 2 runs the full loop.

---

## phase log (retrospective)

### Phase 0 (de facto: foundation slice F)

Walking-skeleton equivalent. Documents, repositories, db wiring, and ccboard package init. No behavior — just the data layer through which every later slice talks.

- `ReactionDocument`, `BoardEntryDocument` in `attu_models`
- `ReactionRepository`, `EntryRepository` with full CRUD + leaderboard aggregations
- `apps/bot/doom_bot/database/__init__.py` — instantiation + wiring of the new repos
- `apps/bot/doom_bot/ccboard/__init__.py` — per-message lock dict, `_pending_bot_removals` echo-suppression set, helper functions

Verified with the existing test suite (1438 tests). No behavior, no new tests.

### Phase 1 (parallel slices, three waves)

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

### Phase 2 (planned)

Auditor (`AuditorTask`) + user-facing `/stars` against ccboard. Runs through the full process loop. See "phase 2 outline" below.

---

## bug log (retrospective + ongoing)

Items found during phase 1 that fell outside their slice's scope. Format:
`[severity · disposition] description`. Triage column filled in by the `bug-triage` skill — see step 2 below for the live pass.

### Surfaced and resolved during phase 1

1. **Sub-agent worktree base race.** `Agent` calls with `isolation: "worktree"` gave parallel sub-agents inconsistent base commits — slice B got the right HEAD, slice M got a May-5 commit 18 commits behind. Worked around with explicit `git reset` instructions in agent prompts and by taking slice M into the main agent. Resolved by hand for phase 1; future spawns use the fail-fast guard pattern.
2. **`ConfigRepository.save_guild` silent default.** New tier-3 fields persisted as default-only because `save_guild`'s doc dict had a fixed key list. Caught by the new ccboard roundtrip test (`tests/python/component/test_db_repositories.py::test_ccboard_roundtrip_through_load_guild`). Fixed in the slice C commit.
3. **Circular import on `tasks/__init__` ↔ `ccboard.manager`.** Path: manager → builder → starboard → `doom_bot/__init__` → `tasks/__init__` → manager (partially init). Fixed by deferring the manager import into `register_bot_tasks()` and switching `from doom_bot import config` to `from doom_bot.client.core import config` in manager.py. Tests caught it on the wave-3 merge.
4. **py-cord 2.x embed proxy nullability.** `discord.Embed.image` and `.footer` return `None` when unset, not an empty proxy — slice B's voice-memo and forwarded tests asserted `.url`/`.text` directly and crashed. Switched to `getattr(..., None)` and `to_dict()` membership.

### Open / awaiting triage

These came from the deferred items I added to `notes/to-do.md` under the ccboard section, plus one looming environmental concern. Triage applied 2026-05-07 via the `bug-triage` skill — severity and disposition follow each entry. Sequence number prefixes match the source list above so the triage section below references them by number.

5. User-facing ccboard slash commands (`/stars random`, `/stars lost`, `/stars recheck`, four leaderboards). Legacy `/stars` still hits the legacy starboard. **Note:** after a guild migrates via `/fix stars convert`, the legacy `/stars` keeps returning results from the now-frozen legacy starboard, but new reactions only land in ccboard — so legacy `/stars` returns increasingly stale data post-migration.
6. Phase 2 auditor (`AuditorTask` with discovery, reconciliation, orphan passes). `/fix ccboard recover` and `/fix ccboard recount` are stubs.
7. Wiki-attribution pass — parse webhook notification messages, resolve wiki usernames to discord user ids via a `wiki_identities` collection.
8. `effective_author_id` re-resolution path. Once set or left None during backfill, never revisited; if the reply target later becomes available (re-fetched, restored from backup), attribution stays stale.
9. Retroactive emoji-weight recalculation. Weight changes don't propagate to existing `ReactionDocument.point_value`. Confirmed: `/fix ccboard regen` rebuilds POSTS but does NOT re-snapshot `point_value` — there is currently no path at all to update point values after a weight change short of users re-reacting.
10. Extension reload policy — keep handlers always loaded gating per call (current), or wire `bot.reload_extension()` into the `enabled` toggle path.
11. Retire `notes/plans/ccboard.md` — superseded by THIS file (the predecessor at the same path was never in git).
12. Dev-tree merge conflict (environmental). The original `dev` worktree has 291 lines of uncommitted edits to `events.py`, plus changes to `modlog.py`, `starboard.py`, `util.py`, `logging.py`, `scheduler.py`, `wiki/client.py`, `webhook.py`, `commands/trees.py`, `tests/conftest.py`, `notes/agents.md`, `notes/to-do.md`, and `uv.lock`. Slice W's edits to `events.py` will conflict on merge.

#### Surfaced during phase 2.2 (added 2026-05-10)

13. Watcher↔auditor concurrent-write integration not proven by test. Both call sites take `ccboard.get_lock(message_id)` against the shared `ccboard._locks` dict, and the watcher's lock pattern is exercised by tests, but no test runs `handle_reaction_add` concurrently with `reconcile_entry` to prove the lock actually serializes them on the same `asyncio.Lock` instance. Inspectionally identical → almost certainly correct, but unverified.
14. `_apply_diff` ignores `_safe_remove_reaction` return values. When discord rejects a remove (rate limit, NotFound, Forbidden), `_safe_remove_reaction` discards the pending key and returns False, but the diff summary still reports `strip_invalid=N` / `strip_extras=N` as if they applied. The DB state is unaffected (strips are best-effort cleanup of reactions that should never have been recorded). Operator-facing metric only.
15. Partial-pagination degradation has unit-test coverage only. `_collect_live_reactions` raises `partial=True` on any `reaction.users()` failure or mid-stream pagination loss; `_compute_diff` then suppresses removes globally. The behavior is unit-tested, but the production codepath against a real flaky discord reaction stream is never exercised.
16. Single flaky emoji blocks all soft-deletes on an entry. `partial=True` from any one emoji's `reaction.users()` failure suppresses removes for **every** emoji on the entry, not just the failing one. Conservative; in practice partial=True is rare. Phantom-vote cleanup for healthy emojis is then deferred until the next reconcile run.

### Triage (2026-05-07)

```
- [important] #5  user-facing /stars commands           → fix-in-phase-2 · post-migration legacy /stars goes stale; pair with auditor
- [important] #6  phase 2 auditor (recover/recount)     → fix-in-phase-2 · this IS phase 2
- [nit]       #7  wiki-attribution pass                 → defer · revisit after phase 2 lands and we have usage data
- [important] #8  effective_author_id re-resolution     → defer · rare (only fires when reply target becomes available later); revisit before ship of phase 2
- [important] #9  retroactive emoji-weight recalc       → fix-in-phase-2 · fold into auditor recount pass with explicit "re-snapshots point_value" semantic
- [nit]       #10 extension reload policy               → defer · current per-call gating works; revisit only if slash-command visibility becomes a problem
- [nit]       #11 retire notes/plans/ccboard.md         → won't-fix · predecessor was never in git, so there is nothing to retire; this entry is the work
- [blocker]   #12 dev-tree merge conflict on events.py  → defer-to-feature-complete · environmental; deferred per user direction 2026-05-07. re-walk on the post-phase-2 ship gate; until then, no merge to dev is attempted
```

**Patterns observed:**

- **Items 5, 6, 8, 9 all stem from "phase 1 ships only the back-end half + admin tools, not the user-facing surface."** That's a deliberate scope cut, not a bug — but it means phase 2 is broader than just "auditor". It's auditor + user-facing `/stars` + retroactive weight recalc + (probably) re-resolution. Hand to `plan-revise`: consider splitting phase 2 into **2a (auditor + recount semantics including weight re-snapshot)** and **2b (user-facing `/stars` against ccboard, with the legacy `/stars` retirement decision)**. The two halves can ship independently.
- **Items 9 and 6 interact at the design level.** The auditor's recount pass is the natural home for retroactive weight recalc, but only if we explicitly decide it re-snapshots `point_value` with current config weights. The plan-revise output for phase 2a should pin that down before implementation, not during.
- **Items 7, 8, 10, 11 are mostly defer/won't-fix.** The bug log reads scarier than it is — the actually-actionable items at the project boundary are the blocker (#12) and the two phase-2 importants (#6, #9).

### Triage (2026-05-10) — phase 2.2 retro

```
- [important] #6  phase 2 auditor (recover/recount)     → fix-in-phase-2.4 · partially satisfied: per-entry recount surface ships in 2.2 via /fix ccboard recount <link>; guild-wide reconcile + scoped discovery is 2.4
- [important] #9  retroactive emoji-weight recalc       → fix-in-phase-2.3 · option B+ semantic locked in; folds into a `to_recount` bucket extending phase 2.2's _compute_diff via the staleness predicate
- [important] #13 watcher↔auditor concurrent lock       → defer · before phase-2 ship gate; add a concurrent-coroutine unit test or live discord smoke check; lock pattern is inspectionally correct but unverified
- [nit]       #14 _apply_diff ignores _safe_remove ret  → defer · operator-facing metric only; revisit if production diffs report strip counts that don't match discord state
- [nit]       #15 partial-pagination live verification  → defer · fold into phase-2 ship gate's live discord smoke check (alongside #13)
- [nit]       #16 single flaky emoji blocks all removes → defer · could sharpen to per-emoji partial flags later; not worth complexity until production shows it bites
```

**Patterns observed (2026-05-10):**

- **Items #13, #14, #15, #16 all share one root: the auditor's apply path landed without a real-discord integration check.** They are not a phase-level rewrite signal — the unit-test contract is solid — they are a phase-2-ship-gate signal. Hand to `plan-revise`: add a "live discord smoke check" line item to the phase-2 ship gate (today's `## ship readiness — ccboard phase 1` section needs a phase-2 sibling) covering: concurrent watcher+auditor on the same message (#13), `_safe_remove_reaction` failure path (#14), partial-pagination from a real flaky stream (#15), and per-emoji partial isolation (#16). One ship-gate checklist item, not four code patches.
- **#6 is now structurally split across phases 2.2 and 2.4.** Per-entry recount surface shipped early; guild-wide discovery is still 2.4. Plan-revise should annotate the split so the eventual "ship readiness for phase 2" entry doesn't double-count this.
- **#9 narrowed.** The retro showed phase 2.2's `_compute_diff` already carries the structure recount needs (a "replace with same emoji + fresh point_value" path is the existing replace bucket). Plan-revise should narrow phase 2.3's scope to (a) data-model adds, (b) config bump, (c) watcher stamp, (d) staleness-predicate bucket folded into reconcile_entry — *not* a parallel codepath.

---

## ship readiness — ccboard phase 1

Applied 2026-05-07 via the `ship-readiness` skill. The cut-line below is the gate for merging `feat/ccboard-redesign` → `dev`.

### Prerequisites

- [x] **integration-check** — full test suite passed at HEAD (`98f7cc3a`): 1302 unit + 154 component + 13 integration + 32 JS = 1501 tests, 0 failures
- [x] **feature-completion** — slice I closed with tests, documentation, configuration plumbing (six-step tier-3), web interface, and lint all clean
- [x] **code-review** — no uncommitted changes other than the intentional `.secrets` symlink (mirrors the dev tree) and `notes/plans/ccboard.md` itself (gitignored by project convention)

### Blockers

- **env: dev-tree merge conflict** — `/srv/services/doom-bot-dev` has uncommitted WIP on `events.py` (291 lines), `modlog.py`, `starboard.py`, `util.py`, `logging.py`, `scheduler.py`, `wiki/client.py`, `webhook.py`, `commands/trees.py`, `tests/conftest.py`, `notes/agents.md`, `notes/to-do.md`, and `uv.lock`. Slice W's edits to `events.py` will conflict on merge. Until the user commits, stashes, or rebases this WIP, `feat/ccboard-redesign` → `dev` is unsafe (silent WIP loss with `--ff-only`, conflict otherwise) · 30 min – 2 hours depending on path

### Deferred (follow-up — phase 2 or beyond)

- [medium] **#5 user-facing `/stars` against ccboard** — phase 2b. Post-migration with `enabled=True`, legacy `/stars` returns frozen pre-migration data; bounded because migration is opt-in and documented in `notes/features/ccboard.md`
- [medium] **#6 phase 2 auditor (`/fix ccboard recover|recount`)** — phase 2a. Drift accumulates only under `enabled=True`; documented as a known gap; `/fix ccboard regen` provides a partial workaround for visual drift but not for missed reactions
- [medium] **#9 retroactive emoji-weight recalculation** — phase 2a, fold into auditor recount with explicit "re-snapshots `point_value`" semantic. Today there is no path at all to update existing `ReactionDocument.point_value` after a `ccboard.emojis` weight change
- [low] **#8 `effective_author_id` re-resolution** — rare edge case (deleted message later restored from backup); add `/fix ccboard reattribute <link>` if real usage surfaces it
- [low] **#7 wiki-attribution pass** — future feature; depends on a `wiki_identities` collection that doesn't exist yet
- [low] **#10 extension reload policy** — current per-call gating works; revisit only if slash-command visibility becomes a problem

Closed at gate (no carry-forward):

- **#11 retire predecessor `notes/plans/ccboard.md`** — already-fixed-just-not-closed: the new plan IS the canonical version; the predecessor was never in git, so there is nothing to retire

### Verdict

**Project boundary deferred until feature-complete (post phase 2).** Per user direction 2026-05-07: phase 1 stays on `feat/ccboard-redesign` and accumulates phase 2 work on the same branch. The dev merge is not the next milestone — feature completion is.

The phase-1 snapshot above is preserved as a record of the wave-3 boundary state. Item #12 (dev-tree WIP conflict) is no longer a current blocker because no merge is pending; it remains in the bug log so it gets re-walked when ship-readiness next runs (after phase 2). New phase-2 commits land on `feat/ccboard-redesign` directly.

---

## phase 2 pre-mortem

Applied 2026-05-09 via the `pre-mortem` skill, replacing the placeholder phase-2 outline. Phase 2 splits into **2a (auditor + recount with `point_value` re-snapshot)** and **2b (user-facing `/stars` against ccboard + legacy `/stars` retirement)** per the bug-triage pattern from 2026-05-07.

**Bottom line:** **proceed with revisions** — three high-severity risks need probes before phase 2.1 starts, plus a load-bearing design decision (recount semantic) needs to be pinned before any recount code is written.

### Risks

#### Phase 2a (auditor + recount)

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

#### Phase 2b (user-facing /stars + legacy retirement)

- [high] **integration** — two `SlashCommandGroup('stars', ...)` registrations cannot coexist in py-cord. the new ccboard-backed /stars must replace, not coexist with, the legacy starboard-backed /stars. but per-guild routing inside one command (legacy if `ccboard.enabled=False`, ccboard if `True`) requires both implementations to live in the same module. probe: prototype a one-command router (`/stars random`) that branches on guild config, verify command tree sync still works, eyeball error paths.
- [high] **premise** — the legacy `/stars` behavior post-migration is an open question. once a guild migrates via `/fix stars convert`, new reactions write only to ccboard, but legacy `/stars random` still queries the (now-frozen) legacy starboard. options: (a) hard-cutover at migration time — flip a guild flag, /stars routes to ccboard, legacy data ignored forever; (b) per-command soft-route — /stars checks `ccboard.enabled` and uses the appropriate backend. (a) is simpler but loses pre-migration visibility; (b) is more code but preserves "old data still browsable". user choice required before 2b code.
- [medium] **scope** — /stars recheck on ccboard requires a per-entry reconciliation function. that function IS phase 2a's reconciliation pass, factored to take a single message_id rather than a guild. mitigation: explicit dependency — 2a's reconciliation lands first; 2b's /stars recheck imports it.
- [medium] **integration** — ccboard /stars random/lost adds entries' response message ids to `display_message_ids` so reactions on the response redirect back to the original. the watcher's redirect resolver already handles this via `entry_repo.get_by_display_message`. but the existing legacy /stars stores a different ref (`response_doc.refs.starboard_post`) — these two redirect paths must not collide. mitigation: ccboard /stars never writes `MessageDocument.refs.starboard_post`; only writes to `BoardEntryDocument.display_message_ids`.
- [medium] **operational** — retiring legacy /stars is a destructive command-tree change. once removed, guilds that haven't migrated lose starboard browsing entirely. mitigation: keep legacy /stars in-tree but no-op routed when `ccboard.enabled=True`; full removal is a separate, much later decision.
- [low] **expertise** — none new; /stars is mostly wiring over existing repo methods (`EntryRepository.get_random`, `leaderboard_*`, `ReactionRepository.leaderboard_most_given`).

#### Cross-phase

- [high] **operational** — order of operations under live use: enable ccboard → migrate via /fix stars convert → users react and post → user runs /stars and gets ccboard-backed result. if 2b ships before 2a's reconciliation, /stars recheck is missing; if 2b ships before legacy retirement is decided, /stars routing is undefined. probe: stage 2a fully (including /fix ccboard recount with re-snapshot semantic decided) before any 2b code lands.

### Walking-skeleton check

The current outline's "AuditorTask registered with empty pass implementations" is a reasonable wiring-only phase 0 for **2a**, but it's not a *full* walking skeleton because it doesn't touch 2b's slash command surface. A real phase 0 for the whole of phase 2 should be:

- `AuditorTask(BaseTask)` registered in `register_bot_tasks()`, `interval=None` (manual-trigger only), `run()` that logs "auditor stub: would-be reconcile" and returns. proves scheduler wiring without a runaway scan.
- `/fix ccboard recover` and `/fix ccboard recount` rewritten from "phase 2 only" stubs to a real call into the auditor's no-op `discover()` / `reconcile()` methods. proves the slash command → task method seam.
- `/cc stars` placeholder slash command group registered (provisional name to dodge legacy conflict), with one stub command `/cc stars test` that responds "phase 2 stub". proves the /stars surface is wireable without colliding with legacy.
- One end-to-end smoke test: enable ccboard on a test guild, invoke `/fix ccboard recount`, see the no-op log line; invoke `/cc stars test`, see the stub response. no real auditor work happens; the seams are proven.

This phase 0 retires no risk on its own, but it surfaces the *layer* problems (scheduler, slash command tree, lock dict access from auditor) before the costly probes run. Every later phase replaces a stub with real implementation; no new layer is introduced after phase 0.

### Phase-order revisions

The placeholder said "reconciliation before discovery, then ?". Risk-first reordering with explicit reasons:

| original (placeholder)              | proposed (risk-first)                                            | reason |
|---|---|---|
| 1. AuditorTask wiring (stubs)       | 1. **walking skeleton** (auditor stubs + /cc stars stub)         | full walking skeleton covers both 2a and 2b layers; placeholder only covered 2a |
| 2. recover (discovery)              | 2. **recount design note + user approval**                       | the highest-severity premise risk is a *decision*, not code. pin the `point_value` semantic before writing any recount code |
| 3. recount (reconciliation)         | 3. **per-entry reconciliation pass (dry-run default)**           | hardest correctness; doing this before bulk discovery proves the diff logic on a controlled input. /fix ccboard recount on one entry, dry-run + confirm gating |
| —                                   | 4. **per-entry recount with re-snapshot** (using approved semantic) | folds the recount semantic into the per-entry path; no bulk re-snapshot until per-entry is proven |
| —                                   | 5. **discovery pass (scoped: recently-active channels only)**    | the unbounded-scan risk is retired by scoping; full-history discovery is a later optional phase |
| —                                   | 6. **orphan-post cleanup with grace period**                     | least urgent (rare in practice); grace period bounds the destructive risk |
| —                                   | 7. **/stars random/lost on ccboard** (replaces legacy by config gate) | depends on builder + entry repo; both already exist |
| —                                   | 8. **/stars leaderboards** (most-stars, most-starred, most-given) | trivial wiring on existing repo methods |
| —                                   | 9. **/stars recheck on ccboard** (calls 2a phase 3 per-entry reconcile) | depends on 2a phase 3; explicit cross-phase dep |
| —                                   | 10. **legacy /stars routing decision** (per-guild gate vs hard cutover) | user decision; pin before any retirement |
| —                                   | 11. **legacy /stars retirement** (no-op route when ccboard.enabled, deletion deferred) | irreversible; ship last, with the option to skip |

Phase 1 of the placeholder ("AuditorTask wiring") and phase 2 ("recount design note") together replace what was a single phase-1 entry — the design note is cheap and unblocks downstream work, so it's its own phase.

### Definition-of-done additions per phase

Each phase ships only when its DoD is met. Placeholder DoDs were per-phase only; the additions below cover cross-phase integration, the unknown-the-phase-was-supposed-to-retire, and a rollback criterion.

- **phase 0 (walking skeleton)** — DoD adds:
  - integration check: bot starts cleanly, scheduler shows AuditorTask, /fix ccboard recover responds with stub message, /cc stars test responds with stub message
  - unknown retired: scheduler+task+slash-command seams for phase 2 are proven wireable
  - rollback: if /cc stars conflicts with legacy /stars at command-sync time, abandon `/cc stars` namespace and use a different placeholder; no code commitment yet
- **phase 1 (recount design note)** — DoD adds:
  - integration check: design note in `notes/plans/ccboard.md` under a new "phase 2.1 — recount semantic" section; user-approved verdict captured (one of: rename `point_value`, add `last_recounted_at`, accept silent drift)
  - unknown retired: the meaning of `point_value` after recount
  - rollback: if user rejects all three options, phase 2 stalls — surface this immediately rather than coding around an undecided semantic
- **phase 2 (per-entry reconciliation, dry-run)** — DoD adds:
  - integration check: dry-run reconcile against a real seeded entry produces a diff summary; no DB mutation observed; watcher continues to write reactions normally during the run (proves lock cooperation)
  - unknown retired: diff logic correctness on a real entry
  - rollback: if dry-run produces nonsensical diffs (e.g., "would remove every reaction"), abandon the diff strategy and redesign before any non-dry-run path lands
- **phase 3 (per-entry recount with re-snapshot)** — REVISED 2026-05-10 after phase 2.2 retro and bug-triage; scope narrowed because phase 2.2's `_compute_diff` already carries the structure recount needs (the existing replace bucket is "soft-delete old + upsert with fresh `point_value`" — exactly recount's mutation). DoD now reads:
  - scope, in order: (a) add `last_recounted_at: int | None = None` to `ReactionDocument` (`packages/shared-models/attu_models/documents.py`); (b) add `weights_updated_at: int = 0` to `GuildCCBoard` (`apps/bot/doom_bot/config.py`) and the `GuildConfigDocument.ccboard` flow; (c) bump `weights_updated_at = int(time.time())` in the web save handler (`apps/bot/doom_bot/web/routes.py`) when `emojis` or `super_bonus` change; (d) stamp `last_recounted_at = now` in the watcher's same-emoji refresh path (`apps/bot/doom_bot/ccboard/watcher.py:381-400`); (e) extend `_compute_diff` (or a sibling helper) with a `to_recount` bucket fed by the staleness predicate `(last_recounted_at or reacted_at) < cfg.weights_updated_at`; (f) reuse `_apply_diff`'s replace-bucket path for `to_recount` items (same emoji, fresh `point_value` from current `cfg.emojis[emoji] + super_bonus`, stamp `last_recounted_at = now`); (g) `recount_entry(guild_id, message_id, dry_run=True)` becomes a thin wrapper around `reconcile_entry` with the to_recount bucket enabled. **explicitly out of scope**: a parallel codepath, a bulk update_many across all guilds, or any change to existing reconcile semantics
  - integration check: recount on one seeded entry uses option B+ (per phase 2.1 verdict); before/after `point_value` deltas logged; `/debug ccboard show_reactions` reflects the new values; records whose `last_recounted_at` already exceeds `weights_updated_at` are untouched
  - unknown retired: re-snapshot mechanics under live config
  - rollback (tightened 2026-05-10): trigger if recount changes `point_value` for any record where the staleness predicate did not match — proves the predicate is wrong, not the apply path. soft-revert via `mark_dirty` and let the manager re-aggregate from the (now-corrected) reaction records; secondary rollback for inconsistent net_points / positive_points unchanged from prior wording
- **phase 4 (discovery, scoped + guild-wide reconcile)** — REVISED 2026-05-10 to absorb the guild-wide half of bug-log #6; phase 2.2 shipped the per-entry recover surface (`/fix ccboard recount <link>`), so this phase owns the remaining `reconcile_guild` stub plus scoped discovery. DoD adds:
  - scope: (a) replace `auditor.reconcile_guild` stub with a real implementation that walks every `BoardEntryDocument` in the guild and calls `reconcile_entry(..., dry_run=True/confirm)` per entry, respecting a per-guild time budget; (b) implement `discover_guild` against the channel set produced by the watcher's recent-reactions cache (scope retired risk); (c) keep `/fix ccboard recover` (already wired to `discover_guild`) unchanged; the "no-link" path of `/fix ccboard recount` (currently the `reconcile_guild` stub) becomes real here
  - integration check: discovery on a single channel completes within a measured time budget (probe output drives the budget); rate-limit waits logged; no `ReactionDocument` created without an existing or newly-created `BoardEntryDocument`; guild-wide reconcile against a seeded ccboard guild produces the same per-entry diffs as running `/fix ccboard recount <link>` over each entry individually
  - unknown retired: discovery cost on a real channel; per-guild budget shape under realistic entry counts
  - rollback: if discovery exceeds the time budget, narrow scope further (last 7 days vs 30) before re-running; never run unbounded; if guild-wide reconcile produces diffs that differ from per-entry reconcile, the iteration order or lock acquisition is wrong — abandon and run per-entry from a slash-command loop instead
- **phase 5 (orphan-post cleanup)** — DoD adds:
  - integration check: dry-run on the ccboard channel produces a list of candidate orphan posts with ages; only posts older than the grace period appear; manual confirmation required before delete
  - unknown retired: orphan detection accuracy
  - rollback: if the dry-run flags posts that are actually current entries (false positive), the diff logic is wrong; abandon the pass before any deletion
- **phase 6 (/stars random/lost)** — DoD adds:
  - integration check: with `ccboard.enabled=True`, /stars random returns an entry from `ccboard_entries`; reaction on the response redirects to the original via `display_message_ids`; legacy /stars still works on `ccboard.enabled=False` guilds
  - unknown retired: routing seam between legacy and ccboard backends
  - rollback: if the routing is wrong (returns ccboard data when legacy was expected), the gate logic is off; revert the routing change without touching repos
- **phase 7 (/stars leaderboards)** — DoD adds:
  - integration check: each leaderboard subcommand returns the expected top-N for a seeded guild; effective_author_id attribution honored; pagination matches the `_PAGE_SIZE` convention
  - unknown retired: aggregation correctness in the user-facing surface (the repo methods are already tested in 2a)
  - rollback: minor, per-command fix
- **phase 8 (/stars recheck)** — DoD adds:
  - integration check: /stars recheck on a single message invokes phase 3's per-entry reconcile path with `confirm=True` semantics; result message mirrors the legacy recheck format
  - unknown retired: surface integration of 2a's reconcile from a slash command
  - rollback: if recheck mutates state unexpectedly (because `confirm=True` is implicit), require explicit confirm before mutating; defer the implicit-confirm UX to a later iteration
- **phase 9 (legacy routing decision)** — DoD adds:
  - integration check: design note in plan with user-approved verdict (per-guild gate vs hard cutover); no code change yet
  - unknown retired: legacy /stars long-term fate
  - rollback: if user is undecided, default to per-guild gate (the more conservative option) — no destructive change to legacy
- **phase 10 (legacy /stars retirement, no-op route)** — DoD adds:
  - integration check: with `ccboard.enabled=True`, legacy /stars subcommands respond "ccboard is active in this guild — use /stars" and don't query legacy starboard repo; with `enabled=False`, legacy /stars works unchanged
  - unknown retired: command coexistence under py-cord
  - rollback: legacy /stars is preserved entirely; only the no-op gate changes; trivial to revert

## phase 2.1 — recount semantic (design note, awaiting user approval)

The `point_value` field on `ReactionDocument` is documented as "snapshot at reaction time" ([packages/shared-models/attu_models/documents.py:176](../../packages/shared-models/attu_models/documents.py#L176)). The phase 2 pre-mortem flagged this as a high-severity premise risk because phase 2.3's recount pass changes that meaning — at minimum, recounted records reflect *current* config weights, not *original* reaction-time weights. Three options for resolving the semantic; one must be chosen before phase 2.3 lands.

### option A — rename `point_value` → `current_point_value`

Make the new semantic explicit in the field name. `point_value` becomes `current_point_value`, documented as "most recent snapshot — refreshed on same-emoji re-react and on auditor recount; reflects the config weight in effect at that moment".

- **callers to update**: watcher (4 sites), migration (3 sites), manager `_sync_post`, `aggregate_points` aggregation, `/debug ccboard show_reactions`, every test that constructs a `ReactionDocument`.
- **migration**: ferretdb `update_many({}, {'$rename': {'point_value': 'current_point_value'}})` against `ccboard_reactions` at startup, then drop on subsequent runs (idempotent).
- **upside**: most honest semantic; no historical-vs-current confusion; field name *is* the documentation.
- **downside**: largest blast radius — touches every site that reads or writes the field, plus a one-shot migration step. Migration risk on a multi-thousand-record collection is bounded but real.

### option B — add `last_recounted_at: int | None = None`

Keep `point_value` but extend its docstring to "snapshot at most recent reaction or recount; check `last_recounted_at` to disambiguate". `last_recounted_at` is `None` for records never recounted (almost all of them today) and a unix timestamp for records the auditor has touched.

- **callers to update**: only the recount pass (writes `last_recounted_at = now`) and `/debug ccboard show_reactions` (displays it).
- **migration**: zero — the field defaults to `None` so existing records read as never-recounted on first load.
- **upside**: smallest blast radius; data model surfaces the semantic to `/debug ccboard show_reactions` and gives leaderboards a tie-break key (recent recount = more authoritative); compatible with all existing tests.
- **downside**: callers that aggregate `point_value` (the manager, the leaderboard repo methods) treat all values uniformly without distinguishing "old config snapshot" from "current config snapshot". The semantic is *available* in the model but not *enforced*; misuse possible.

### option C — silent drift

Document in `notes/features/ccboard.md` that `point_value` reflects the most recent snapshot (reaction-time *or* recount-time, whichever is later). No code or schema change. Same-emoji re-react already refreshes `point_value`, so the drift exists today; the recount pass just extends it to records the user hasn't touched.

- **callers to update**: zero.
- **migration**: zero.
- **upside**: zero cost, zero risk.
- **downside**: invisible in the data model; future readers of `ReactionDocument` won't notice the semantic without reading the doc; `/debug ccboard show_reactions` cannot display "this was recounted" because there's no field for it.

### recommendation

**option B**. Smallest blast radius, surfaces the semantic in the data model (so `/debug ccboard show_reactions` can flag recounted records), and gives leaderboards a tie-break key without a schema rename. Option A is the cleanest semantic but the migration cost is exactly the kind of "phase-late surprise" the pre-mortem exists to surface; option C is operationally cheapest but invisible to anyone reading the model later.

### verdict — option B+ (chosen 2026-05-09)

**Approved with refinement.** The naive option B would recount *every* record on each invocation. The refinement ("option B+") makes recount **targeted**: only records whose `point_value` snapshot predates the most recent weight change get recomputed.

Two model changes:

- **`ReactionDocument.last_recounted_at: int | None = None`** — set to `now` whenever the watcher refreshes a record in place (same-emoji re-react) and whenever the auditor's recount stamps it. `None` means "never refreshed beyond original `reacted_at`".
- **`GuildCCBoard.weights_updated_at: int = 0`** — bumped to `now` whenever an admin saves a change that affects per-reaction value: `emojis` or `super_bonus`. The web `routes.py` save path is the natural bump site; an audit-log entry already fires there. Default `0` so the first recount after this field rolls out treats every pre-existing record as potentially stale.

Staleness predicate (used by phase 2.3 recount):

```
is_stale(reaction, cfg) := (reaction.last_recounted_at or reaction.reacted_at) < cfg.weights_updated_at
```

Recount per record:

```
new_value = cfg.emojis[reaction.emoji_str] + (cfg.super_bonus if reaction.is_super else 0)
if new_value != reaction.point_value:
    reaction.point_value = new_value
reaction.last_recounted_at = now
```

Behavior implications captured here so phase 2.3 doesn't relitigate:

- **Watcher's same-emoji re-react** ([watcher.py:381-400](../../apps/bot/doom_bot/ccboard/watcher.py#L381-L400)) must also write `last_recounted_at=now`. Without it, a user who re-reacts after a weight change has a fresh `point_value` but no fresh marker, and the staleness predicate would (harmlessly but pointlessly) flag it for recount.
- **Different-emoji vote change** writes a new `ReactionDocument` with `reacted_at=now`, so `last_recounted_at=None` is fine — the staleness predicate falls back to `reacted_at`, which is `now`, so it's not stale.
- **Migration** (`/fix stars convert`) creates new records with the current config weights, so `last_recounted_at=None` is correct (`reacted_at` reflects the migration time and is by definition >= any prior `weights_updated_at`).
- **Aggregations** (`aggregate_points`, leaderboards) ignore `last_recounted_at` entirely — they only sum `point_value`. The new field is observability-only at the manager/leaderboard layer.
- **`/debug ccboard show_reactions`** can display "recounted YYYY-MM-DD" next to records where `last_recounted_at is not None`.

This pushes phase 2.3's scope: it's not a "for every record, recompute" loop — it's a "for every stale record, recompute" loop. Discovery (phase 2.4) and orphan cleanup (phase 2.5) are unaffected. Phase 2.2 (per-entry reconcile) is also unaffected since reconcile is about discord ↔ DB diff, not point arithmetic.

Schema-wise, `last_recounted_at` is added to `ReactionDocument` as `int | None = None` (no migration; defaults absorb pre-existing records). `weights_updated_at` is added to `GuildCCBoard` as `int = 0` and to `GuildConfigDocument.ccboard` likewise; the web form save bumps it. The web tier-3 form does not need a UI control — the field is a derived audit timestamp, not user-editable. Audit logging on the existing `compare_configs + log_audit` path will pick it up automatically.

**Verdict:** approved, with the option B+ refinement above. Phase 2.2 (per-entry reconcile) and phase 2.3 (per-entry recount + watcher stamp + config bump) are both unblocked; phase 2.3 carries the data-model and config-bump work. Risk-first ordering still puts phase 2.2 before 2.3 because reconcile is the harder correctness problem.

---

## phase 2 process loop

The placeholder's "1..n with the per-phase loop" still applies after these revisions. Each of phases 0-10 above runs:

1. **plan** — definition-of-done explicitly includes a cross-phase integration check (see DoD additions above)
2. **programmer** — implementation; bug-log anything found out-of-scope
3. **integration-check** — `integration-check` skill against fixtures, perf budgets, and the running watcher/manager (concurrent reads must not deadlock the auditor)
4. **phase-retro** — `phase-retro` skill output captures surprises; feeds the next two steps
5. **bug-triage + plan-revise** — refresh the bug log section above; revise downstream phases if a premise no longer holds

Ship gate at the end of phase 10 (or after a phase-2a-only ship if 2b is split off): **`ship-readiness`** before merging `feat/ccboard-redesign` → `dev`. The dev-tree WIP merge conflict (#12) is re-walked at that gate.

---

## critical files (current state)

Created during phase 1:

- `apps/bot/doom_bot/ccboard/{__init__,watcher,manager,builder,migration}.py`
- `tests/python/unit/test_ccboard_{builder,watcher,manager}.py`
- `tests/python/component/test_ccboard_manager.py`
- `tests/python/component/test_commands_fix_stars_convert.py`
- `notes/features/ccboard.md`

Modified during phase 1:

- `packages/shared-models/attu_models/{documents,repositories,__init__}.py`
- `apps/bot/doom_bot/database/__init__.py`
- `apps/bot/doom_bot/config.py`
- `apps/bot/doom_bot/web/{forms,routes}.py`
- `apps/bot/legacy_web/templates/guild_config.html`
- `apps/bot/legacy_web/static/js/app.js`
- `apps/bot/doom_bot/client/events.py`
- `apps/bot/doom_bot/tasks/__init__.py`
- `apps/bot/doom_bot/commands/{fix,debug}.py`
- `notes/agents.md`, `notes/to-do.md`

---

## verification

Phase 1 ships once these pass after the dev merge:

1. ruff check, ruff format --check, basedpyright clean.
2. `docker compose run --build --rm --quiet-pull tests` — 1501 tests across unit / component / integration / JS.
3. Toggle `enabled=False`: no observable difference vs. the legacy starboard. Old system continues to react to events.
4. Toggle `enabled=True` via the web UI: reload watcher reloads guild config; ccboard handlers begin recording reactions on next event.
5. `/fix stars convert` populates `ccboard_reactions` and `ccboard_entries` from the existing starboard. Idempotent.
6. React with a configured emoji on a fresh message → `ReactionDocument` recorded; ~60s after settle, manager creates a board post with `{n} {points_label} | {jump_url}`.
7. Vote change (different emoji) → old emoji removed at its `source_*` location; new `ReactionDocument` active; old soft-deleted; no echo cascade.
8. Same-emoji re-react after a missed remove → `ReactionDocument` refreshed in place; no discord removal; user not locked out.
9. Self-star (including on a bot message attributed to a user) → reaction auto-removed.
10. Multi-image post → all embeds share `url=jump_url`, render as a connected gallery.
11. Drop below threshold then recover → post deleted, `starboard_message_id` cleared, recreated when threshold met again.
12. Sweep at 3 / 5 / 11 consecutive same-author posts → embed announcement in ccboard channel; one announcement only at each threshold.

End-to-end discord verification (steps 3-12) requires a guild with `ccboard.enabled=True` and is gated on the user's go-ahead.

---

## phase 2.2 retro — 2026-05-10

Applied via the `phase-retro` skill against commit `133e96f5`. Inputs to `bug-triage` follow this section; downstream-phase edits flow into `plan-revise`.

### spec delta

- delivered: per-entry reconcile via `reconcile_entry(guild_id, message_id, dry_run=True)` plus `/fix ccboard recount <link> [confirm]`. pure `_compute_diff` (seven outcome buckets: add / replace / remove / matching / strip_invalid / strip_extras / partial flag), `_apply_diff` apply path, lock cooperation via `ccboard.get_lock(message_id)`, partial-pagination degradation, watcher's `_safe_remove_reaction` reused for self/bot/extras stripping. unit + component tests cover dry-run, apply, partial, no-change, missing entry, disabled cfg, unfetchable message, invalid-link, cross-guild rejection.
- missed / deferred:
  - **DoD integration check #3 (lock cooperation under live watcher activity) — not exercised.** The lock pattern is inspectionally identical to the watcher's, but no test runs a `handle_reaction_add` concurrently with a `reconcile_entry` to prove the per-message lock actually serializes them. → bug-log; either add a concurrent unit test using two coroutines on the same `asyncio.Lock`, or fold a real-discord smoke check into the phase 2 ship gate.
- extra (beyond DoD):
  - **apply path landed** — DoD specified dry-run only (rollback criterion was "if dry-run produces nonsensical diffs, abandon"). apply was added opportunistically with a `confirm=True` gate. not a problem in practice — diffs were sane — but the rollback criterion could not have fired since `dry_run=False` paths bypassed that check.
  - one-vote-per-message enforcement (`to_strip_extras`) added to the diff. the watcher already enforces this on event handling; reconcile now mirrors it.
  - duplicate `aggregate_points` call in the apply path was caught and fixed pre-commit (per handoff). near-miss; logged below.

### surprises

- assumption: dry-run is the cautious path and apply lands later → reality: apply was wired the same session under a `confirm=True` gate → delta: phase 2.2 collapsed phases 2.2 and what would have been 2.2b. phase 2.3 (recount) inherits a working apply-path scaffold rather than having to introduce one.
- assumption: `_compute_diff` would be a flat add/remove pair → reality: it grew to seven discrete outcome buckets to handle one-vote enforcement, self/bot stripping, and partial-pagination degradation in one structured pass → delta: the structure makes phase 2.3 recount easier — recount is "another bucket fed from the staleness predicate" rather than a parallel codepath.
- assumption: `partial=True` would only ever come from a single-emoji failure → reality: `_collect_live_reactions` raises `partial=True` on any per-emoji `reaction.users()` failure OR mid-stream pagination loss; `_compute_diff` then suppresses **all** removes globally, not just per-emoji → delta: more conservative than the pre-mortem mitigation called for. unlikely to bite (production almost never hits partial), but worth noting that a single flaky emoji blocks every soft-delete on the entry.
- assumption: the unit test harness could exercise component flows with monkeypatches → reality: invoking `pytest tests/python/component/...` directly outside docker hits `ServerSelectionTimeoutError` on `ferret:27017`; component tests must go through `scripts/run_tests.py` (which auto-redirects through `docker compose run`) → delta: workflow gotcha, not a phase 2.2 issue, but agents-in-the-future will keep tripping on this if they assume pytest runs locally.
- duplicate `aggregate_points` call in the apply path made it into the working tree before commit. caught by inspection, not by tests (both calls returned the same value). → delta: structural review beats test review for "calls happen exactly once" assertions.

### residual debt

- **watcher↔auditor concurrent-write integration not proven by test.** lock pattern is inspectionally correct; needs a concurrent-coroutine test or live smoke check before phase 2 ship gate. · routed to bug log as #13
- **`reconcile_guild` is still a stub.** `/fix ccboard recount` without a `<link>` falls through to it; phase 2.4 (scoped discovery) absorbs this. · already in bug log as part of #6
- **`_apply_diff` ignores `_safe_remove_reaction` return values.** if a discord remove fails, the diff summary still claims `strip_invalid=N` / `strip_extras=N` were applied. safe-remove logs the failure internally, so the operator can find it; counter is misleading though. · routed to bug log as #14
- **partial-pagination degradation has unit test coverage only.** simulating `reaction.users()` mid-stream failure against a real discord requires an unhappy fixture. not blocking phase 2.3; flag for phase 2 ship gate. · routed to bug log as #15
- **single-flaky-emoji blocks all soft-deletes on an entry.** the partial-mode global remove suppression is conservative; if one emoji's pagination fails, valid removes for other emojis on the same entry are also suppressed. · routed to bug log as #16

### implications for downstream phases

- **phase 2.3 (recount) is wider open than originally scoped.** the apply path already handles "soft-delete old, upsert with fresh `point_value`" for the replace bucket — that is exactly recount's per-entry mutation. recount becomes "feed the staleness predicate's matches into the replace bucket with the same emoji" rather than an entirely new helper. plan-revise should narrow phase 2.3's scope to: (a) add `last_recounted_at` to `ReactionDocument`, (b) add `weights_updated_at` to `GuildCCBoard`, (c) bump `weights_updated_at` in the web save handler, (d) stamp `last_recounted_at` in the watcher's same-emoji refresh, (e) extend `_compute_diff` (or a sibling) with a `to_recount` bucket fed by the staleness predicate, (f) fold into `reconcile_entry` so `/fix ccboard recount <link>` does both reconcile *and* recount in one pass.
- **the rollback criterion "if dry-run produces nonsensical diffs" should be tightened for phase 2.3** to "if recount changes `point_value` for records where the staleness predicate didn't match" — proving the predicate is the load-bearing question.
- **bug log items #5, #6, #9 from the 2026-05-07 triage** all converge on the same machinery now. plan-revise can mark #6 as partially satisfied (per-entry recover surface ships in 2.2; guild-wide is 2.4) and #9 as squarely phase-2.3 work.

---

## revision after phase 2.2 — 2026-05-10

Applied via the `plan-revise` skill against the phase 2.2 retro (above) and the 2026-05-10 triage block in the bug log.

what changed:

- phase 3 (per-entry recount): **revise** — scope narrowed to fold into phase 2.2's `_compute_diff` via a `to_recount` bucket fed by the staleness predicate; data-model + watcher-stamp + web-save-bump items spelled out in the DoD; rollback criterion tightened to "recount changed `point_value` for a record the predicate didn't match"
- phase 4 (discovery, scoped): **revise** — absorbs the still-stub `reconcile_guild` (the no-link path of `/fix ccboard recount`); guild-wide reconcile is now half of phase 4's scope alongside scoped discovery; closes the remaining half of bug-log #6
- phases 0, 1, 2: complete (delivered as 2.0, 2.1, 2.2)
- phases 5-10: **valid** — no premise shifted; revisit at each phase's start

new section added:

- **`## phase 2 ship gate` (below)** — captures the live discord smoke checks that bug-triage clustered under #13/#14/#15/#16. one ship-gate checklist, not four code patches.

follow-up questions raised by the retro that this revision did NOT answer:

- phase 2.3 (e) above lists "extend `_compute_diff` (or a sibling helper)" — the helper-vs-extension call is left to phase-2.3 implementation. either is fine; mention it here so the implementer doesn't treat it as undecided design.
- the phase-2 ship gate checklist (below) names four live-discord verifications that require a guild with `ccboard.enabled=True`. timing of that smoke check (after 2.5? after 2.8? right before merge?) is left for the user to pick when phase 2.5 wraps.

---

## phase 2 ship gate

Created 2026-05-10 alongside the phase 2.2 plan-revise. Parallel to `## ship readiness — ccboard phase 1` above; the phase-1 entry remains as a record of the wave-3 boundary. This section is the pre-merge gate for `feat/ccboard-redesign` → `dev` after **all** of phase 2 (phases 2.3 through 2.5 at minimum; phases 2.6+ are optional and can ship in a separate gate per the 2026-05-07 phase-2a/2b split).

The mechanical checks (ruff / basedpyright / `scripts/run_tests.py` all green) are a precondition, not part of this gate.

### Live discord smoke checks

These cover the bug-log items that the unit and component tests cannot exercise (#13–#16 from the 2026-05-10 triage). Each is a manual check against a real guild with `ccboard.enabled=True`; expected to be one focused session.

1. **Watcher↔auditor concurrent lock cooperation (#13).** Add a real reaction to a tracked message **while** `/fix ccboard recount <link> confirm:True` is running on that same message. Expected: no duplicate `ReactionDocument`, no missed soft-delete, no point-aggregate corruption. Watch the log for two `ccboard auditor: reconcile_entry` events and one `ccboard: reaction add` event interleaved without errors. Failure mode: a `KeyError` or a "phantom" reaction that persists past the next manager tick.
2. **`_safe_remove_reaction` failure path (#14).** Force a `discord.HTTPException` from `message.remove_reaction` (revoke `Manage Messages` on the bot mid-recount, or rate-limit via repeated /fix runs). Expected: the diff summary still reports `strip_invalid=N` / `strip_extras=N`, the discord reaction stays put, and `_pending_bot_removals` is left clean (the watcher's `discard_pending_removal` call ran). Failure mode: a stuck pending key would cause the next remove echo to be eaten silently.
3. **Real flaky pagination (#15).** Run `/fix ccboard recount <link>` against a message with a high-volume reaction (>200 of one emoji is enough to fan out into a paginated `users()` call) while the bot is approaching its global rate limit. Expected: any pagination failure surfaces `partial=True` in the summary and the apply path skips removes; never produces a "would remove every reaction" diff. Failure mode: a partial pagination silently treated as complete would soft-delete real reactions.
4. **Per-emoji partial isolation (#16).** Reproduce a partial-mode reconcile and verify (via the log) that **all** removes are suppressed, not just the failing emoji's. This is the conservative behavior we shipped — the smoke check is to confirm it, not to break it. Failure mode: if removes for healthy emojis ARE applied during a partial run, the conservative invariant is broken and #16 needs immediate redesign before merge.

### Other gates (carry-forward from phase 1's ship-readiness)

- `integration-check` skill against the running watcher/manager/auditor stack
- `bug-triage` re-walk of the open bug log (re-evaluate #8, #13, #14, #15, #16 — at least #13 should leave the log resolved)
- dev-tree merge conflict (#12) gets re-walked here per the 2026-05-07 verdict
- final `code-review` over the cumulative phase-2 diff
- `feature-completion` checklist clean across the whole phase (tests, docs, config plumbing, web interface, lint)

### Verdict format (filled in at gate time)

| ship-or-no? | rationale |
|---|---|
| _(filled in by `ship-readiness` skill at the gate)_ | _(blockers, deferred items, follow-ups)_ |

---

## metadata

```yaml
last_updated: 2026-05-10
status: phase 2.2 landed; retro + bug-triage + plan-revise complete; phase 2.3 unblocked with narrowed scope (folds into phase 2.2's _compute_diff via staleness-predicate bucket); phase-2 ship gate scaffold added
```
