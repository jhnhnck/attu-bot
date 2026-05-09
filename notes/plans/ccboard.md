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

## phase 2 outline

When phase 2 starts, run the full loop:

1. **Pre-mortem** via the `pre-mortem` skill on the auditor design. The auditor has scary unknowns: discovery scans channel history (rate-limit-sensitive), reconciliation must match live discord reactions against `ccboard_reactions` (consistency tricky), orphan pass reasons over the bot's own posts (deletion is destructive). Risk-first ordering applies.
2. **Phase 0 walking skeleton** — `AuditorTask(BaseTask)` registered but with empty pass implementations. Verifies scheduling, lock acquisition with the watcher running concurrently, and that `/fix ccboard recover/recount` reach the stubs.
3. **Phases 1..n** — most uncertain first. Probably reconciliation pass before discovery (fewer code paths, but the diff logic between live discord state and our DB is the actually-hard part).
4. **Bug log** — kept in this file under "open / awaiting triage".
5. **Per-phase loop** — programmer → `feature-completion` → `integration-check` → `phase-retro` → `bug-triage` + `plan-revise`.
6. **Ship gate** — `ship-readiness` before phase 2 merges to `dev`.

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

## metadata

```yaml
last_updated: 2026-05-07
status: phase 1 landed on feat/ccboard-redesign; project boundary deferred until feature-complete per user direction; phase 2 work continues on the same branch
```
