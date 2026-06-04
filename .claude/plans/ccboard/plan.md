# ccboard — replacement reaction board

Forward-looking spec + per-phase status. THE canonical doc for the ccboard project; edited in place. Retros, plan-revises, and the ship gate live in [log.md](log.md); the adversarial review lives in [pre-mortem.md](pre-mortem.md); the bug log lives in [bugs.md](bugs.md). Reference doc for shipped behavior: [notes/features/ccboard.md](../../../notes/features/ccboard.md).

Branch: `feat/ccboard` (restarted 2026-06-04 from tag `archive/ccboard-redesign`, which preserved the discarded `feat/ccboard-redesign` history). Phases 0–2.3 are already implemented in the checked-out tree.

## goals
- replace the legacy starboard with a configurable signed-emoji board: per-guild `ccboard.emojis` is `dict[str, int]`; positive weights count toward threshold, negative weights reduce `net_points` but never block posting.
- per-message reaction state survives missed events — same-emoji re-react self-heals via in-place refresh; aggregate gaps recovered by the auditor.
- bot-attributable messages credit the originating user via `effective_author_id` (self-star check, leaderboards, sweeps all use the resolved author).
- migration is opt-in and idempotent: `/fix stars convert` requires `confirm=True` + non-empty `ccboard.emojis`; re-running yields the same state.
- ships behind a default-off `GuildCCBoard.enabled` flag — no legacy behavior change until a guild flips it.
- all existing tests still pass at every phase boundary (phase 1 shipped at 1501 tests; phase 2.3 at 1346 unit / 160 component / 13 integration / 32 JS).

## non-goals
- deleting legacy `/stars` or the legacy starboard module — kept in-tree, no-op-routed when ccboard is active; physical deletion deferred indefinitely (phase 2.10).
- wiki-attribution resolution (parsing webhook author → discord id via a `wiki_identities` collection) — out of initial scope; manual-only/future (bug #7).
- full-history discovery scans — discovery is scoped to recently-active channels only; unbounded scans are explicitly rejected.
- `effective_author_id` re-resolution after first backfill (bug #8) — deferred.
- merging `feat/ccboard` → `dev`/`trunk` — gated behind the phase-2 ship gate; not part of building the plan.

## constraints
- py-cord 2.x: two `SlashCommandGroup('stars', ...)` registrations cannot coexist — new ccboard `/stars` must replace, not coexist with, legacy (per-guild routing inside one module).
- FerretDB v2 / DocumentDB backend — see `ferretdb-quirks`; component tests must run via `scripts/run_tests.py` (docker), not bare pytest (hits `ServerSelectionTimeoutError`).
- discord API rate limits bound the auditor's discovery/reconcile scans (≈50 req/s global, 5 req/2s per route).
- no push, no deploy, no discord interaction without explicit user instruction (CLAUDE.md rules).
- branch is `feat/ccboard` (was `feat/ccboard-redesign`, archived). all phase-2 work lands here directly until the ship gate.
- environmental: the `dev` worktree carries uncommitted WIP on `events.py` (+ others) that will conflict on an eventual merge (bug #12) — deferred to the ship gate per user direction 2026-05-07.

## accepted risks
The phase-2 pre-mortem (in [pre-mortem.md](pre-mortem.md)) surfaced three high-severity risks now mitigated by design: the unbounded discovery scan is bounded by scoping discovery to recently-active channels (phase 2.4); the destructive reconcile-against-discord is gated by `dry_run=True` default + `confirm=True` + a partial-pagination degrade-to-no-removes path (shipped 2.2); and the recount `point_value` semantic was pinned to "option B+" (targeted staleness-predicate recount, shipped 2.3) before any recount code landed. Two high-severity open risks remain probes for the phases that own them: discovery cost on a real guild (phase 2.4) and the py-cord single-`/stars`-group routing seam (phase 2.6). Operator-facing reconcile diagnostics (#14, #17) and the `PLR0912` ceiling (#19) are accepted debt with named homes.

## phase 0 — foundation (walking skeleton)
**status:** closed (foundation slice F; verified at 1438 tests, no behavior)
**definition of done:** data layer end-to-end — every later slice talks through these repos.
**scope:** `ReactionDocument`/`BoardEntryDocument` in `attu_models`; `ReactionRepository`/`EntryRepository` (CRUD + leaderboard aggregations); db `__init__` wiring; `ccboard/__init__.py` (per-message lock dict, `_pending_bot_removals` set).

## phase 1 — back-end + admin tools
**status:** closed (three waves; integration at 98f7cc3a, 1501 tests)
**definition of done:** `enabled=False` → zero observable change; `enabled=True` → reactions recorded, posts built/synced, migration populates both collections idempotently.
**scope:** tier-3 config plumbing for `GuildCCBoard` (six steps); builder rule pipeline (10 rules, multi-image gallery fix); `/fix stars convert` migration; watcher (4 raw handlers, redirect/backfill/one-vote/echo-suppression); `ManagerTask` (10s poll, 60s settle, five `_sync_post` branches, sweep counter); `/fix ccboard {regen,purge}`, `/debug ccboard show_reactions`; `notes/features/ccboard.md`.

## phase 2.0 — phase-2 walking skeleton
**status:** closed (f749a6ee)
**definition of done:** scheduler + slash-command seams for the auditor and the `/stars` surface proven wireable without real scan work.
**scope:** `AuditorTask(BaseTask)` registered manual-only; `/fix ccboard {recover,recount}` wired to no-op auditor methods; `/cc stars` placeholder stub (dodges legacy `/stars` conflict).

## phase 2.1 — recount semantic design note
**status:** closed (2ddc7df0 note; 69e7b189 verdict — option B+)
**definition of done:** user-approved verdict on what `point_value` means after recount.
**scope:** design note comparing rename / add-`last_recounted_at` / silent-drift; verdict = **option B+** (add `last_recounted_at` + `weights_updated_at`; recount is targeted by a staleness predicate, not blanket). full verdict preserved in [log.md](log.md).

## phase 2.2 — per-entry reconcile (dry-run default)
**status:** closed (133e96f5)
**definition of done:** dry-run reconcile of a seeded entry yields a sane diff with no mutation while the watcher keeps writing (lock cooperation); `confirm=True` applies.
**scope:** `reconcile_entry(guild_id, message_id, dry_run=True)`; pure `_compute_diff` (seven buckets: add/replace/remove/matching/strip_invalid/strip_extras/partial); `_apply_diff`; `/fix ccboard recount <link> [confirm]`; partial-pagination degrade-to-no-removes; reuse watcher `_safe_remove_reaction`.

## phase 2.3 — per-entry recount with re-snapshot
**status:** closed (199a703c)
**definition of done:** recount on a seeded entry uses option B+ — only staleness-predicate matches change `point_value`; non-stale records untouched; `show_reactions` reflects new values.
**scope:** add `ReactionDocument.last_recounted_at`; add `GuildCCBoard.weights_updated_at` (+ bump in both web save paths when `emojis`/`super_bonus` change); stamp `last_recounted_at` in watcher same-emoji refresh; `to_recount` bucket fed by `_is_stale`; `recount_entry` as thin wrapper. out of scope: parallel codepath, bulk update_many.

## phase 2.4 — guild-wide reconcile + scoped discovery + show_reactions ext
**status:** pending commit

**definition of done:** discovery on one channel completes within a measured time budget (rate-limit waits logged, never unbounded); no `ReactionDocument` created without a `BoardEntryDocument`; guild-wide reconcile produces the same per-entry diffs as running `/fix ccboard recount <link>` per entry; post-`weights_updated_at`-bump, guild-wide recount re-snapshots every stale active record and leaves fresh ones untouched.
**scope:** real `reconcile_guild` (walks every `BoardEntryDocument`, calls `reconcile_entry` per entry under a per-guild time budget — recount inherited free via the staleness predicate); real `discover_guild` against the watcher's recent-reactions channel set; the no-link path of `/fix ccboard recount` becomes real; extend `/debug ccboard show_reactions` to render `last_recounted_at` (closes #18). out of scope: any change to `reconcile_entry`/`_compute_diff`.
**rollback:** discovery over budget → narrow scope (7d vs 30d), never unbounded; recount changes a non-stale record → stale `cfg` per iteration, revert to per-entry; guild-wide diffs differ from per-entry → lock acquisition wrong, revert to slash-command loop.

## phase 2.5 — orphan-post cleanup (grace period)  ← NEXT
**status:** open
**definition of done:** dry-run on the ccboard channel lists candidate orphan posts with ages; only posts older than the grace period appear; manual confirm required before any delete.
**scope:** `cleanup_orphans` (dry-run default, 7-day grace, log every deletion). implementation note (#19): if orphan signals fold into `_compute_diff`, extract another `_classify_*` helper or `# noqa: PLR0912 — <reason>`; silently bumping the lint limit is not acceptable.
**rollback:** dry-run flags a current entry as orphan → diff logic wrong, abandon before any deletion.

## phase 2.6 — /stars random/lost on ccboard
**status:** open
**definition of done:** with `enabled=True`, `/stars random` returns a `ccboard_entries` entry; a reaction on the response redirects to the original via `display_message_ids`; `enabled=False` guilds keep legacy `/stars`.
**scope:** ccboard-backed `/stars random|lost` replacing legacy by config gate; append response ids to `display_message_ids` (cap 20); never write `MessageDocument.refs.starboard_post`. probe first: one-command router branching on guild config, verify command-tree sync.
**rollback:** routing returns ccboard data when legacy expected → gate logic off; revert routing without touching repos.

## phase 2.7 — /stars leaderboards
**status:** open
**definition of done:** each leaderboard subcommand returns expected top-N for a seeded guild; `effective_author_id` attribution honored; pagination matches `_PAGE_SIZE`.
**scope:** `/stars leaderboard {most-stars,most-starred,most-given,top-messages}` over existing tested repo methods.

## phase 2.8 — /stars recheck on ccboard
**status:** open
**definition of done:** `/stars recheck <link>` invokes phase-2.2's per-entry reconcile with `confirm=True`; result message mirrors legacy recheck.
**scope:** wire `/stars recheck` to `reconcile_entry`. explicit cross-phase dep on 2.2.
**rollback:** unexpected mutation → require explicit confirm before mutating.

## phase 2.9 — legacy /stars routing decision
**status:** open
**definition of done:** design note + user-approved verdict (per-guild gate vs hard cutover); no code.
**scope:** decision only. default to per-guild gate (conservative) if undecided.

## phase 2.10 — legacy /stars retirement (no-op route)
**status:** open
**definition of done:** with `enabled=True`, legacy `/stars` responds "ccboard is active — use /stars" without querying legacy repo; with `enabled=False`, legacy `/stars` unchanged.
**scope:** no-op gate only; legacy module preserved entirely; physical removal is a separate later decision. ship last; skippable.

## phase 2 ship gate
After phase 2.5 (minimum; 2.6+ may ship in a separate gate per the 2a/2b split), run `ship-readiness` before merging `feat/ccboard` → `dev`. The gate's live-discord smoke checks (#13–#16) and carry-forward items are recorded in full in [log.md](log.md) under "phase 2 ship gate". Mechanical checks (ruff / basedpyright / `scripts/run_tests.py` green) are a precondition, not part of the gate.
