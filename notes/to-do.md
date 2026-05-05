# general doom bot to-do list

_see the [meta](#meta) section at the end of this file for format reference._

---

## tasks

### self

- `medium priority` `low effort` assign any to-dos without an effort or category; update priorities; move completed and sort all
- `medium priority` `low effort` run docker tests with --coverage flag; update coverage in second section; update testing to-dos with gaps
- `low priority` `medium effort` update docs, notes, and readme; reorganize and consolidate notes
- `low priority` `low effort` scan for files over ~300 lines; add to-do items for any that should be split up
- `medium priority` `low effort` scan codebase for TODO and FIXME comments; add any new items to the to-do list

### eggs / hatch game

- ⭕ `future idea` `high effort` slight rebrand of the game into "hatch!"
- ⭕ `future idea` `high effort` way to discard/recycle hatches back into eggs, loot box style
- ⭕ `medium priority` `medium effort` /eggs show: link to first egg message in thread instead of just the thread

### starboard

- ⭕ `medium priority` `medium effort` bug: starboard doesn't render multiple images from messages with more than one attachment (from cowboy)
- ⭕ `medium priority` `medium effort` add a /stars command to show which starboard messages have the most stars (not users)
- ⭕ `medium priority` `medium effort` /stars leaderboard results should be paginated with the same buttons as the wiki results.
- ⭕ `medium priority` `medium effort` add optional filters to /stars random and /stars lost for like user, and min stars for random, which emoji (might have to be by name)
- ⭕ `medium priority` `high effort` stickers, voice memos still have rendering issues. with the latter not showing the no preview text bit either. the gif links aren't showing right either, they include a png instead of the gif/gifv.

### wiki

- ⭕ `medium priority` `low effort` bug: wiki lookup pagination allows negative index via rapid button clicks — `_prev_callback`/`_next_callback` have no bounds check; the `disabled` state only rebuilds after the async wiki fetch, so concurrent clicks bypass it; corrupted index persists to db (from banarnar)
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

### web interface

see `notes/plans/web_improvement.md` for the full 7-step restructure plan and `notes/reports/web_interface_audit.md` for the current state audit.

- ⭕ `medium priority` `medium effort` fix everywhere we're currently displaying raw snowflakes

### maintenance

- ⭕ `medium priority` `medium effort` audit command descriptions and make sure they make sense, match style guide, only say needed/user-facing details; add completions; improve interface, add embeds where it makes sense
- ⭕ `medium priority` `medium effort` move hard-coded but constant settings into toml config files; load them through `NovaConfig` instead of scattering magic values across the codebase
- ⭕ `medium priority` `medium effort` trace initialization steps and ensure all data loading flows through `NovaConfig` primarily; reduce branching that makes startup order hard to follow
- ⭕ `low priority` `low effort` bug: `time_advance` passes `cfg.guild.id` to `scheduler.add_job` but `GuildConfig` has no `.guild` attr; should be `cfg.id` (`commands/time.py:34`)
- ⭕ `low priority` `low effort` bug: pycord `DeprecationWarning` on python 3.13 — `asyncio.get_event_loop()` called without a running loop (`discord/client.py:250`); will break on a future python version. upstream issue, may need a pycord upgrade or workaround
- ⭕ `low priority` `medium effort` make debug logging filterable; support filtering by module name matching `__name__` via env var
- ⭕ `low priority` `low effort` check for spelling across all notes / code
- ⭕ `low priority` `low effort` add an `ASSETS_PATH` env var and use it directly instead of deriving the path from the config file's parent each time
- ⭕ `low priority` `low effort` move guild-level calendar property to the guild object (`client/calendar.py:175`)
- ⭕ `future idea` `high effort` switch ingestor vector store to hybrid search with BM25 sparse; requires collection schema migration (`ingestor/vector_store.py:51`)
- ⭕ `future idea` `very high effort` refactor out ferret and just use postgres + documentdb?

### code audits

- `low effort` scan for security issues and vulnerabilities; check for OWASP top 10, injection risks, auth gaps, and insecure dependencies

### testing

- ⭕ `medium priority` `medium effort` add tests for tasks/nova_year.py (57%)
- ⭕ `medium priority` `medium effort` add tests for client/migrations.py (30%) - schema migration runner and version logic
- ⭕ `low priority` `low effort` split up large test files into focused modules by feature or command group
- ⭕ `low priority` `medium effort` add tests for wiki/pages.py (21% coverage) - page fetch and parsing

---

## completed tasks

### scheduling / signals

- 🔴 `4 May 2026` fix(signals): web reload signals dropped in prod and reminder task firing inconsistently; ingestor was inheriting all bot tasks via module-import side effects in `attubot/tasks/__init__.py`, racing the bot for the `reload_signals` collection on every poll. moved registration into a `register_bot_tasks()` function called from `client/events.py`, and split signals per consumer with a `target` field so the bot and ingestor each consume only their own queue. schema bumped to 2.5.5 with `migration_target_signals` to drop the legacy index and purge untargeted docs.

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

- 🔴 `26 April 2026` implement web improvement plan — sidebar layout, guild toggle, session-based active guild, split guild config pages (channels/epoch/roles/users/starboard) with per-section PATCH endpoints, SSR helpers, save manager with dirty tracking, legacy redirects
- 🔴 `11 April 2026` enforce web audit logging — replaced optional `if web_app.audit_logger:` guards with `log_audit()` helper; added error-path and missing-route audit coverage

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

## coverage

| Statements | Miss | Branch | Branch Parts | Coverage |
|------:|-----:|-------:|-------:|------:|
| 8951 | 2542 | 2192 | 244 | 69% |

### attubot

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/__init__.py | 12 | 0 | 0 | 0 | 100% |
| attubot/config.py | 462 | 143 | 86 | 23 | 65% |
| attubot/logging.py | 73 | 22 | 8 | 0 | 63% |
| attubot/signals.py | 16 | 1 | 2 | 1 | 89% |

### attubot/client

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/client/__init__.py | 57 | 4 | 6 | 0 | 94% |
| attubot/client/calendar.py | 129 | 13 | 40 | 5 | 87% |
| attubot/client/core.py | 12 | 0 | 0 | 0 | 100% |
| attubot/client/embeds.py | 27 | 1 | 16 | 1 | 95% |
| attubot/client/events.py | 263 | 155 | 76 | 2 | 38% |
| attubot/client/families.py | 36 | 0 | 8 | 0 | 100% |
| attubot/client/logo.py | 18 | 2 | 2 | 1 | 85% |
| attubot/client/markers.py | 148 | 39 | 46 | 6 | 68% |
| attubot/client/messages.py | 329 | 30 | 120 | 5 | 92% |
| attubot/client/migrations.py | 291 | 193 | 58 | 1 | 30% |
| attubot/client/modlog.py | 325 | 62 | 142 | 40 | 77% |
| attubot/client/starboard.py | 580 | 168 | 226 | 44 | 69% |
| attubot/client/util.py | 56 | 11 | 10 | 1 | 73% |
| attubot/client/years.py | 74 | 0 | 16 | 0 | 100% |

### attubot/commands

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/commands/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/commands/chat.py | 151 | 120 | 40 | 0 | 16% |
| attubot/commands/debug.py | 215 | 31 | 38 | 4 | 86% |
| attubot/commands/eggs.py | 246 | 12 | 72 | 5 | 95% |
| attubot/commands/fix.py | 492 | 278 | 126 | 11 | 42% |
| attubot/commands/link.py | 110 | 24 | 12 | 1 | 80% |
| attubot/commands/marker.py | 82 | 9 | 16 | 2 | 89% |
| attubot/commands/query.py | 33 | 2 | 8 | 0 | 95% |
| attubot/commands/remind.py | 89 | 21 | 20 | 1 | 76% |
| attubot/commands/stars.py | 202 | 27 | 38 | 3 | 88% |
| attubot/commands/time.py | 43 | 2 | 4 | 0 | 96% |
| attubot/commands/wiki.py | 152 | 42 | 30 | 4 | 69% |
| attubot/commands/year.py | 89 | 8 | 34 | 4 | 90% |

### attubot/database

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/database/__init__.py | 72 | 4 | 0 | 0 | 94% |
| attubot/database/connection.py | 53 | 0 | 10 | 0 | 100% |
| attubot/database/models.py | 202 | 0 | 0 | 0 | 100% |
| attubot/database/repositories.py | 599 | 149 | 102 | 10 | 72% |

### attubot/eggs

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/eggs/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/eggs/data.py | 4 | 4 | 0 | 0 | 0% |
| attubot/eggs/emojis.py | 52 | 0 | 8 | 0 | 100% |
| attubot/eggs/hatching.py | 155 | 6 | 50 | 5 | 94% |

### attubot/ingestor

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/ingestor/__init__.py | 32 | 26 | 2 | 0 | 18% |
| attubot/ingestor/embedder.py | 24 | 13 | 4 | 0 | 39% |
| attubot/ingestor/llm.py | 48 | 34 | 18 | 0 | 21% |
| attubot/ingestor/pipelines/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/ingestor/pipelines/discord.py | 194 | 194 | 76 | 0 | 0% |
| attubot/ingestor/pipelines/wiki.py | 93 | 93 | 26 | 0 | 0% |
| attubot/ingestor/query_expander.py | 22 | 11 | 2 | 0 | 46% |
| attubot/ingestor/registry.py | 16 | 16 | 2 | 0 | 0% |
| attubot/ingestor/reranker.py | 21 | 13 | 4 | 0 | 32% |
| attubot/ingestor/summarizer.py | 50 | 50 | 8 | 0 | 0% |
| attubot/ingestor/tasks.py | 34 | 34 | 4 | 0 | 0% |
| attubot/ingestor/vector_store.py | 34 | 23 | 6 | 0 | 28% |

### attubot/tasks

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/tasks/__init__.py | 25 | 0 | 0 | 0 | 100% |
| attubot/tasks/base.py | 13 | 3 | 0 | 0 | 77% |
| attubot/tasks/chat_init.py | 31 | 18 | 0 | 0 | 42% |
| attubot/tasks/db_backup.py | 73 | 0 | 20 | 0 | 100% |
| attubot/tasks/egg_cleanup.py | 50 | 8 | 16 | 3 | 83% |
| attubot/tasks/error_hook.py | 50 | 0 | 8 | 0 | 100% |
| attubot/tasks/logo_update.py | 67 | 0 | 10 | 1 | 99% |
| attubot/tasks/message_backfill.py | 167 | 46 | 48 | 6 | 72% |
| attubot/tasks/nova_year.py | 123 | 49 | 40 | 1 | 57% |
| attubot/tasks/presence.py | 28 | 0 | 2 | 0 | 100% |
| attubot/tasks/reload_watcher.py | 53 | 3 | 16 | 2 | 93% |
| attubot/tasks/reminder.py | 106 | 7 | 40 | 2 | 94% |
| attubot/tasks/scheduler.py | 113 | 19 | 36 | 6 | 82% |

### attubot/web

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/web/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/web/app.py | 126 | 19 | 6 | 2 | 84% |
| attubot/web/audit.py | 81 | 21 | 22 | 3 | 71% |
| attubot/web/auth.py | 258 | 80 | 60 | 6 | 69% |
| attubot/web/discord_integration.py | 105 | 4 | 26 | 5 | 93% |
| attubot/web/forms.py | 202 | 26 | 68 | 6 | 82% |
| attubot/web/routes.py | 556 | 91 | 134 | 21 | 83% |

### attubot/wiki

| Module | Statements | Miss | Branch | Branch Parts | Coverage |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/wiki/__init__.py | 15 | 5 | 2 | 0 | 59% |
| attubot/wiki/admin.py | 23 | 0 | 2 | 0 | 100% |
| attubot/wiki/auth.py | 19 | 0 | 0 | 0 | 100% |
| attubot/wiki/client.py | 22 | 0 | 0 | 0 | 100% |
| attubot/wiki/models.py | 29 | 0 | 2 | 0 | 100% |
| attubot/wiki/pages.py | 70 | 53 | 12 | 0 | 21% |
| attubot/wiki/search.py | 29 | 0 | 0 | 0 | 100% |

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

### sections

- **to-do** - active items grouped by area; sorted within each section by priority (high first)
- **completed** - done items kept for reference; sorted chronologically; pruned when no longer relevant
- **coverage** - latest test coverage; update by running tests with `--coverage` in docker
- **meta** - this section; describes the doc format and holds recurring maintenance tasks

### metadata

```yaml
last_updated: 4 May 2026
total_completed: 71
```
