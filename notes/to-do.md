# general doom bot to-do list

_see the [meta](#meta) section at the end of this file for format reference._

---

## tasks

### self

- `medium priority` `low effort` assign any to-dos without an effort or category; update priorities; move completed and sort all
- `medium priority` `low effort` run docker tests with --coverage-json flag; run through coverage_report.py to update notes/coverage.md; update testing to-dos with gaps
- `low priority` `medium effort` update docs, notes, and readme; reorganize and consolidate notes
- `low priority` `low effort` scan for files over ~300 lines; add to-do items for any that should be split up
- `medium priority` `low effort` scan codebase for TODO and FIXME comments; add any new items to the to-do list
- ⭕ `medium priority` `low effort` post-merge: reconcile `.gitignore` with `notes/dev/process.md` — the doc says plans live in `notes/plans/<project>.md` (implying tracked) but `.gitignore:56-57` ignores `notes/plans/` and `notes/reports/`. either drop those gitignore lines so plans/reports are tracked, or update the process doc to reflect that they're local-only. handle once the dev-tree WIP merges so we're not editing both trees in parallel

### eggs / hatch game

- ⭕ `future idea` `high effort` slight rebrand of the game into "hatch!"
- ⭕ `future idea` `high effort` way to discard/recycle hatches back into eggs, loot box style
- ⭕ `medium priority` `medium effort` /eggs show: link to first egg message in thread instead of just the thread

### starboard

- ⭕ `medium priority` `medium effort` bug: starboard doesn't render multiple images from messages with more than one attachment (from cowboy) — fixed for ccboard via shared `embed.url` on the gallery; legacy starboard still affected
- ⭕ `medium priority` `medium effort` add a /stars command to show which starboard messages have the most stars (not users)
- ⭕ `medium priority` `medium effort` /stars leaderboard results should be paginated with the same buttons as the wiki results.
- ⭕ `medium priority` `medium effort` add optional filters to /stars random and /stars lost for like user, and min stars for random, which emoji (might have to be by name)
- ⭕ `medium priority` `high effort` stickers, voice memos still have rendering issues. with the latter not showing the no preview text bit either. the gif links aren't showing right either, they include a png instead of the gif/gifv. — fixed for ccboard via dedicated rules; legacy starboard still affected

### ccboard

all phases shipped on `feat/ccboard` (pending merge): foundation models/repos, builder, tier-3 config, watcher with echo suppression + echo-suppression, manager + sweeps, `/fix stars convert` migration, `/fix ccboard {regen,purge}`, `/debug ccboard show_reactions`, per-entry reconcile + recount (2.2/2.3), guild-wide reconcile + scoped discovery (2.4), orphan-post cleanup (2.5), `/stars {random,lost,leaderboard,recheck}` with per-guild ccboard/legacy gate (2.6–2.8), legacy-retirement routing (2.9/2.10). ccboard-cutover prep also shipped: `starboard.enabled` gate + web toggle + migration runbook. `ccboard.enabled=False` is the default; legacy starboard remains active until a guild opts in. 🎯 carried in from plan: ccboard (2026-06-05)

- ⭕ `high priority` `medium effort` before enabling ccboard on any production guild, run the watcher↔auditor concurrent-lock smoke check: add a real reaction to a tracked message while `/fix ccboard recount <link> confirm:True` runs on the same message; verify no duplicate `ReactionDocument`, no phantom, no point-aggregate corruption. this is the live-discord verification that unit tests cannot cover. 🎯 carried in from plan: ccboard #13 (2026-06-05)
- ⭕ `medium priority` `medium effort` wiki-attribution pass: parse the wiki editor username from webhook notification messages (first markdown link, pattern `[Username](wiki-url)`) and resolve to a discord user via a `wiki_identities` collection. gated behind a separate flag or manual-only trigger. 🎯 carried in from plan: ccboard #7 (2026-06-05)
- ⭕ `medium priority` `medium effort` `effective_author_id` re-resolution path: backfill misses do not retroactively update once the reply target becomes available. add a periodic sweep or a `/fix ccboard reattribute <link>` command. 🎯 carried in from plan: ccboard #8 (2026-06-05)
- ⭕ `medium priority` `low effort` decide on extension reload vs. always-loaded: today the ccboard handlers gate on `enabled` per call. if slash command visibility becomes a concern, register guild-scoped commands or wire `bot.reload_extension()` into the reload watcher's `ccboard.enabled` diff. 🎯 carried in from plan: ccboard #10 (2026-06-05)
- ⭕ `low priority` `low effort` `_apply_diff` strip-count reporting: when `_safe_remove_reaction` fails (discord HTTP error), the diff summary still reports `strip_invalid=N`/`strip_extras=N` as applied even though the remove was silently skipped. operator metric only; no data impact. 🎯 carried in from plan: ccboard #14 (2026-06-05)
- ⭕ `low priority` `low effort` partial-pagination degradation not verified on real discord: `_collect_live_reactions` sets `partial=True` on any pagination failure; `_compute_diff` globally suppresses removes. path is unit-tested and conservative; production-against-flaky-stream codepath not smoke-tested. 🎯 carried in from plan: ccboard #15 (2026-06-05)
- ⭕ `low priority` `low effort` per-emoji partial isolation: a single flaky emoji sets `partial=True` on the whole entry, suppressing removes for every emoji — including healthy ones. conservative; sharpen to per-emoji flags if production shows it bites. 🎯 carried in from plan: ccboard #16 (2026-06-05)
- ⭕ `low priority` `low effort` per-record `point_value` delta logging missing: `_apply_diff` logs only the aggregate `recount=N` line; add a debug-log line per record showing before/after `point_value` whenever a recount changes it. land as a small standalone patch anytime. 🎯 carried in from plan: ccboard #17 (2026-06-05)
- ⭕ `low priority` `low effort` pre-existing import-sort error in `tests/python/unit/test_run_tests.py` fails `ruff check` on the whole repo. auto-fixable: `ruff check --fix tests/python/unit/test_run_tests.py`. land as a standalone `chore: ruff` commit. 🎯 carried in from plan: ccboard #21 (2026-06-05)

### wiki

- ⭕ `medium priority` `medium effort` add optional filters to /wiki random to restrict to pages within a category
- ⭕ `low priority` `medium effort` add where you can cycle through the different sections on the page (up and down arrows maybe?)

### chat / ask

- ⭕ `high priority` `low effort` remove `is_bot_owner` guard on `/ask` before public release (`commands/chat.py:109`)
- ⭕ `high priority` `medium effort` add Qdrant + ingestor services to docker-compose; deploy Phase 1 foundation
- ⭕ `high priority` `medium effort` complete wiki ingestion pipeline and validate retrieval quality before moving to Phase 2
- ⭕ `medium priority` `high effort` implement Discord ingestion pipeline - reply chain traversal, time-window grouping, and Claude Haiku summarization (Phase 2)
- ⭕ `medium priority` `medium effort` add option to ignore specific time periods for the discord ingestor
- ⭕ `medium priority` `low effort` add `llm_api_key` to `ChatConfig`; wire as Bearer token in `LLMClient` for both llama-server instances (Phase 2)
- ⭕ `medium priority` `high effort` implement PDF/DOCX document ingestion pipeline with shared volume watching (Phase 3)
- ⭕ `medium priority` `high effort` implement image captioning pipeline via Claude Haiku vision (Phase 3)
- ⭕ `medium priority` `medium effort` add `/fix chat forget` - chunk search, confirmation embed, Qdrant hard delete, `chat_sources` flagging (Phase 4)
- ⭕ `medium priority` `low effort` add `/debug chat status` - Qdrant collection sizes, last ingest times, pending queue depth (Phase 4)
- ⭕ `medium priority` `medium effort` wire LLM failover - 30s timeout then failover from desktop GPU to server CPU (Phase 4)
- ⭕ `low priority` `medium effort` wire `/wiki lookup` to query Qdrant in addition to MediaWiki search
- ⭕ `low priority` `low effort` wire `on_raw_message_delete` to mark the owning `chat_sources` record as stale
- ⭕ `low priority` `medium effort` split up `command_ask` into smaller functions - currently flagged by PLR0912/PLR0915 (`commands/chat.py:112`)
- ⭕ `future idea` `low effort` display image URLs in `/ask` responses; `file_path` already stored in Qdrant payload, ready to swap in

### debug commands

- ⭕ `low priority` `low effort` audit debug commands for embed/theme consistency — `/debug version` already uses `make_embed` and bot theme; several others (message_stats, dump_config, dump_starboard, eggs_show, previews) respond with plain text

### moderation / logging

- ⭕ `medium priority` `medium effort` add kick, ban, and timeout commands

### maintenance

- ⭕ `medium priority` `medium effort` audit command descriptions and make sure they make sense, match style guide, only say needed/user-facing details; add completions; improve interface, add embeds where it makes sense
- ⭕ `medium priority` `medium effort` move hard-coded but constant settings into toml config files; load them through `NovaConfig` instead of scattering magic values across the codebase
- ⭕ `medium priority` `medium effort` trace initialization steps and ensure all data loading flows through `NovaConfig` primarily; reduce branching that makes startup order hard to follow
- ⭕ `low priority` `medium effort` make debug logging filterable; support filtering by module name matching `__name__` via env var
- ⭕ `low priority` `low effort` check for spelling across all notes / code
- ⭕ `low priority` `low effort` add an `ASSETS_PATH` env var and use it directly instead of deriving the path from the config file's parent each time
- ⭕ `low priority` `low effort` move guild-level calendar property to the guild object (`client/calendar.py:175`)
- ⭕ `future idea` `high effort` switch ingestor vector store to hybrid search with BM25 sparse; requires collection schema migration (`ingestor/vector_store.py:51`)
- ⭕ `future idea` `very high effort` refactor out ferret and just use postgres + documentdb?

### code audits

- `low effort` scan for security issues and vulnerabilities; check for OWASP top 10, injection risks, auth gaps, and insecure dependencies

### testing

- ⭕ `medium priority` `high effort` add tests for commands/fix.py (42%) - 492 statements, 278 missed across the largest command module
- ⭕ `medium priority` `high effort` add tests for client/events.py (38%) - 264 statements, 156 missed across discord event handlers
- ⭕ `medium priority` `medium effort` add tests for tasks/nova_year.py (57%)
- ⭕ `medium priority` `medium effort` add tests for client/migrations.py (33%) - schema migration runner and version logic
- ⭕ `medium priority` `medium effort` add tests for client/starboard.py (69%) - 168 missed statements; reaction cascade and embed rendering paths
- ⭕ `medium priority` `medium effort` add tests for client/markers.py (68%) - 39 missed statements in marker parsing/validation
- ⭕ `medium priority` `medium effort` add tests for shared-models/attu_models/repositories.py (69%) - 167 missed statements across repository methods
- ⭕ `low priority` `medium effort` add tests for client/modlog.py (77%) - 62 missed statements in mod log embed/event paths
- ⭕ `low priority` `medium effort` add tests for tasks/message_backfill.py (71%) - 49 missed statements in batched fetch loop
- ⭕ `low priority` `medium effort` add tests for commands/wiki.py (69%) - 42 missed statements in lookup pagination view
- ⭕ `low priority` `medium effort` add tests for commands/trees.py (73%) - 65 missed statements across link/share/unshare paths
- ⭕ `low priority` `low effort` add tests for config.py (65%) - 135 missed statements; gaps mostly in error paths and toml round-tripping
- ⭕ `low priority` `low effort` split up large test files into focused modules by feature or command group
- ⭕ `low priority` `medium effort` add tests for wiki/pages.py (21%) - page fetch and parsing

---

## completed tasks

### scheduling / signals

- 🔴 `4 May 2026` fix(signals): web reload signals dropped in prod and reminder task firing inconsistently; ingestor was inheriting all bot tasks via module-import side effects in `doom_bot/tasks/__init__.py`, racing the bot for the `reload_signals` collection on every poll. moved registration into a `register_bot_tasks()` function called from `client/events.py`, and split signals per consumer with a `target` field so the bot and ingestor each consume only their own queue. schema bumped to 2.5.5 with `migration_target_signals` to drop the legacy index and purge untargeted docs.

### egg related

- 🔴 eggs leaderboard for most complete hatched set and most hatched total
- 🔴 task to clean up non-egg messages in the egg threads
- 🔴 refactor all custom emojis into a single place, and have all be configurable
- 🔴 `11 April 2026` remove remaining references to egg/hatch season or date
- 🔴 `11 April 2026` egg give dropbox pagination with "more" entry that loads next 24 (verified already implemented; stale to-do removed)
- 🔴 `30 March 2026` check audit log in `on_message_delete` to skip modlog for bot-initiated cleanup deletes
- 🔴 `30 March 2026` split /eggs leaderboard into two separate commands: most hatched total and most complete set
- 🔴 `30 March 2026` create `hatch.toml` for egg game tuning; load all tuning values through `NovaConfig` instead of hardcoding
- 🔴 `30 March 2026` make hatch spawn pools data-driven from `hatch.toml`; move all rarity pools and creatures out of `eggs/data.py`
- 🔴 `3 April 2026` /eggs progress: set embed title to user's egg collection

### starboard

- 🔴 `3 April 2026` group /stars leaderboard commands (most-stars, most-starred, most-given) under a /stars leaderboard subgroup for consistency with /eggs leaderboard
- 🔴 `11 April 2026` fix self-star cascade bug: starring the starboard mirror post when your star created it no longer removes the original from the board

### family trees

- 🔴 `26 April 2026` replace /link family trees with /trees — hmac-signed native tree editor integration; link/show/share/unshare commands with role mapping; bumped config_version to 2.5.4
- 🔴 `4 May 2026` restore /link family commands (list, view, set, upload) alongside /trees; familyecho client and FamilyDocument/FamilyRepository back; both command groups coexist

### reminders

- 🔴 `11 April 2026` /remind command: pings you when a specific attu year and optionally day-month rolls around (from walt)

### code audits

- 🔴 `30 March 2026` audit for anything not properly using our systems: scheduler, config, db, commands, files organized correctly, etc
- 🔴 `30 March 2026` audit event-driven tasks and code; identify design improvements and best practices gaps
- 🔴 `30 March 2026` analyze the coverage report and audit what code we're missing and if it needs to have test cases
- 🔴 `30 March 2026` assess whether `NovaConfig` should be split into a sub-package with separate classes for guild, global, theme, hatch game, etc
- 🔴 `30 March 2026` audit starboard; learn from our mistakes to mould a better more fault tolerant, resilient system
- 🔴 `30 March 2026` check code for backwards compat interfaces, see which ones we can remove/refactor out
- 🔴 `30 March 2026` audit codebase for non-standard or inconsistent terminology and decide whether to standardize
- 🔴 `30 March 2026` investigate unifying stored date types under one class (`config.py:108`)

### web interface

- 🔴 `11 April 2026` enforce web audit logging — replaced optional `if web_app.audit_logger:` guards with `log_audit()` helper; added error-path and missing-route audit coverage
- 🔴 `26 April 2026` implement web improvement plan — sidebar layout, guild toggle, session-based active guild, split guild config pages (channels/epoch/roles/users/starboard) with per-section PATCH endpoints, SSR helpers, save manager with dirty tracking, legacy redirects
- 🔴 `20 July 2026` feat(web): drop legacy quart web interface — deleted `doom_bot/web/`, `legacy_web/`, 7 web unit/integration test files; removed `legacy-web` service from both compose files; dropped quart/quart-rate-limiter/hypercorn/webauthn from pyproject.toml

### maintenance

- 🔴 `12 April 2026` decouple TOML config version from db migration version; split `__schema__` and `__config_version__`; move migration runner into `migrations.py`
- 🔴 deploy script (scripts/deploy.py)
- 🔴 `30 March 2026` fix deploy script not pushing version tag alongside trunk
- 🔴 `30 March 2026` catch import errors in deploy.py and suggest fix command
- 🔴 `30 March 2026` fix deploy script not fast-forwarding trunk to version tag without --deploy
- 🔴 `30 March 2026` fix deploy rollback not undoing version bump commit and tag on dev
- 🔴 `30 March 2026` change backfill task to debug logging; report start and end only
- 🔴 `31 March 2026` deploy script doesn't exit cleanly on ctrl+c
- 🔴 `31 March 2026` deploy.py --revert option; takes a version tag, resets trunk to that commit, and rebuilds containers
- 🔴 `31 March 2026` update run_tests.py to match the polish of deploy.py - better output, timing, clear pass/fail summary
- 🔴 `31 March 2026` add progress bars / step output to run_tests.py
- 🔴 `3 April 2026` switch dockerfile base image to `ghcr.io/astral-sh/uv:python3.13-trixie` and replace pip usage with uv
- 🔴 `3 April 2026` add a `once` run option to `BaseTask`
- 🔴 `11 April 2026` remove meaningless `GIT_CHANGED` line-count from dockerfile version string (always 0 on tagged deploys)
- 🔴 `11 April 2026` centralize hard-coded custom emojis into `ui_emojis` guild config with web interface and `ui_emoji()` helper
- 🔴 `4 May 2026` deploy.py --deploy with no bump arg: resume mode that just restarts containers and pushes when trunk is already at the new tag; bump step also git-adds uv.lock now

### testing

- 🔴 `3 April 2026` add tests for client/messages.py - build_message_doc, edit/delete log embeds
- 🔴 `11 April 2026` add tests for tasks/scheduler.py — add_job, start_all, stop_all, dynamic scheduling, error handling, properties (46% → 82%)
- 🔴 `11 April 2026` add tests for commands/marker.py (30%)
- 🔴 `11 April 2026` fix js test count in run_tests.py — `extract_counts` now uses `re.findall` + last match for correct vitest count
- 🔴 `12 April 2026` add tests for commands/debug.py (33% → 86%) and commands/time.py (40% → 96%)
- 🔴 `12 April 2026` add tests for tasks/logo_update.py (32% → 99%) and tasks/error_hook.py (31% → 100%)
- 🔴 `12 April 2026` add tests for tasks/reminder.py (40% → 94%)
- 🔴 `12 April 2026` add tests for commands/query.py (37% → 95%) and commands/stars.py (58% → 88%)
- 🔴 `12 April 2026` add tests for client/families.py (36% → 100%) and database/connection.py (59% → 100%)
- 🔴 `12 April 2026` add tests for web/discord_integration.py (37% → 93%)
- 🔴 `12 April 2026` add tests for tasks/presence.py (63% → 100%) and wiki/client.py (59% → 100%)

---

## meta

### format

open item: `- ⭕ \`priority\` \`effort\` description`

completed item: `- 🔴 \`26 March 2026\` description`

priority levels (highest to lowest): `high priority`, `medium priority`, `low priority`, `future idea`

effort levels: `no effort`, `low effort`, `medium effort`, `high effort`, `very high effort`

items without a checkbox are recurring; they repeat each maintenance cycle rather than being tracked as one-time work. these live in the `## meta` section.

when an item is completed, move it to the `# completed` section under the appropriate category, strip the priority/effort tags, and add a date stamp. sort completed entries chronologically within each category (oldest first). remove completed entries that are no longer relevant and not referenced by any open to-do. increment `total_completed` in the metadata each time an item is marked done.

when adding a new item, sort it into the appropriate section by topic, or add a new section if none fits. assign priority and effort tags. if the scope, priority, or effort is unclear, ask clarifying questions before adding. split larger projects into multiple entries.

bugs go in `notes/bugs.md`, not here. this file is for features, refactors, audits, and other forward work; defects go to the bug log so the `bug-triage` skill can cut them.

### sections

- **to-do** - active items grouped by area; sorted within each section by priority (high first)
- **completed** - done items kept for reference; sorted chronologically; pruned when no longer relevant
- **coverage** - latest test coverage; update by running tests with `--coverage` in docker
- **meta** - this section; describes the doc format and holds recurring maintenance tasks

### metadata

```yaml
last_updated: 20 July 2026
total_completed: 73
```
