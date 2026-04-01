# general doom bot to-do list

_see the [meta](#meta) section at the end of this file for format reference._

---

## tasks

### self

- `medium priority` `low effort` assign any to-dos without an effort or category; update priorities; move completed and sort all
- `medium priority` `low effort` run docker tests with --coverage flag; update coverage in second section; update testing to-dos with gaps
- `low priority` `medium effort` add more stats to web interface
- `low priority` `medium effort` update docs, notes, and readme; reorganize and consolidate notes
- `low priority` `low effort` scan for files over ~300 lines; add to-do items for any that should be split up
- `medium priority` `low effort` scan codebase for TODO and FIXME comments; add any new items to the to-do list

### eggs / hatch game

- ⭕ `future idea` `high effort` slight rebrand of the game into "hatch!"
- ⭕ `future idea` `high effort` way to discard/recycle hatches back into eggs, loot box style
- ⭕ `medium priority` `low effort` remove any remaining references to egg/hatch season or date
- ⭕ `medium priority` `low effort` /eggs progress: set embed title to "user's egg collection" instead of default
- ⭕ `medium priority` `medium effort` /eggs show: link to first egg message in thread instead of just the thread
- ⭕ `medium priority` `medium effort` egg give dropbox crashes with exception when over 25 items; add a *more* entry that loads next 24 in a loop

### starboard

- ⭕ `medium priority` `low effort` group /stars leaderboard commands (most-stars, most-starred, most-given) under a /stars leaderboard subgroup for consistency with /eggs leaderboard
- ⭕ `medium priority` `medium effort` add a /stars command to show which starboard messages have the most stars (not users)
- ⭕ `medium priority` `medium effort` /stars leaderboard results should be paginated with the same buttons as the wiki results.
- ⭕ `medium priority` `medium effort` add optional filters to /stars random and /stars lost for like user, and min stars for random, which emoji (might have to be by name)
- ⭕ `medium priority` `high effort` stickers, voice memos still have rendering issues. with the latter not showing the no preview text bit either. the gif links aren't showing right either, they include a png instead of the gif/gifv.

### wiki

- ⭕ `medium priority` `medium effort` add optional filters to /wiki random to restrict to pages within a category
- ⭕ `low priority` `medium effort` add where you can cycle through the different sections on the page (up and down arrows maybe?)

### chat / ask

- ⭕ `high priority` `low effort` remove `is_bot_owner` guard on `/ask` before public release (`commands/chat.py:109`)
- ⭕ `high priority` `medium effort` add Qdrant + ingestor services to docker-compose; deploy Phase 1 foundation
- ⭕ `high priority` `medium effort` complete wiki ingestion pipeline and validate retrieval quality before moving to Phase 2
- ⭕ `medium priority` `high effort` implement Discord ingestion pipeline - reply chain traversal, time-window grouping, and Claude Haiku summarization (Phase 2)
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

### moderation / logging

- ⭕ `medium priority` `medium effort` add kick, ban, and timeout commands

### web interface

- ⭕ `medium priority` `medium effort` fix everywhere we're currently displaying raw snowflakes for
- ⭕ `medium priority` `medium effort` web audit log should be enforced, not optional - currently guarded by `if web_app.audit_logger:` which silently skips auditing if not configured
- ⭕ `low priority` `medium effort` primary / secondary guild toggle instead of having all guilds

### maintenance

- ⭕ `medium priority` `medium effort` audit command descriptions and make sure they make sense, match style guide, only say needed/user-facing details; add completions; improve interface, add embeds where it makes sense
- ⭕ `medium priority` `medium effort` we use hard-coded custom emojis in a lot of the responses; centralize this into one place; already storing some emoji ids with the theme
- ⭕ `medium priority` `medium effort` move hard-coded but constant settings into toml config files; load them through `NovaConfig` instead of scattering magic values across the codebase
- ⭕ `medium priority` `medium effort` trace initialization steps and ensure all data loading flows through `NovaConfig` primarily; reduce branching that makes startup order hard to follow
- ⭕ `low priority` `medium effort` make debug logging filterable; support filtering by module name matching `__name__` via env var
- ⭕ `low priority` `low effort` check for spelling across all notes / code
- ⭕ `low priority` `low effort` add an `ASSETS_PATH` env var and use it directly instead of deriving the path from the config file's parent each time
- ⭕ `low priority` `low effort` move guild-level calendar property to the guild object (`client/calendar.py:175`)
- ⭕ `low priority` `low effort` add a `once` run option to `BaseTask` (`tasks/base.py:19`)
- ⭕ `future idea` `high effort` switch ingestor vector store to hybrid search with BM25 sparse; requires collection schema migration (`ingestor/vector_store.py:51`)
- ⭕ `future idea` `very high effort` refactor out ferret and just use postgres + documentdb?

### code audits

- `low effort` scan for security issues and vulnerabilities; check for OWASP top 10, injection risks, auth gaps, and insecure dependencies

### testing

- ⭕ `medium priority` `medium effort` add tests for tasks/scheduler.py (29% coverage) - task scheduling, cancellation, restart logic
- ⭕ `medium priority` `medium effort` add tests for commands/link.py (25%) and commands/marker.py (30%)
- ⭕ `medium priority` `medium effort` add tests for commands/debug.py (30%) and commands/time.py (40%)
- ⭕ `medium priority` `medium effort` add tests for tasks/logo_update.py (38%) and tasks/error_hook.py (35%)
- ⭕ `medium priority` `medium effort` add tests for tasks/nova_year.py (57%)
- ⭕ `medium priority` `high effort` add tests for client/messages.py (60% coverage) - build_message_doc, edit/delete log embeds
- ⭕ `low priority` `low effort` split up large test files into focused modules by feature or command group
- ⭕ `low priority` `low effort` add tests for client/families.py (36%) and database/connection.py (59%)
- ⭕ `low priority` `medium effort` add tests for wiki/pages.py (17% coverage) - page fetch and parsing
- ⭕ `low priority` `medium effort` add tests for web/discord_integration.py (37% coverage)
- ⭕ `low priority` `medium effort` add tests for commands/query.py (37%) and commands/stars.py (58%)

---

## completed tasks

### egg related

- 🔴 eggs leaderboard for most complete hatched set and most hatched total
- 🔴 task to clean up non-egg messages in the egg threads
- 🔴 refactor all custom emojis into a single place, and have all be configurable
- 🔴 `30 March 2026` check audit log in `on_message_delete` to skip modlog for bot-initiated cleanup deletes
- 🔴 `30 March 2026` split /eggs leaderboard into two separate commands: most hatched total and most complete set
- 🔴 `30 March 2026` create `hatch.toml` for egg game tuning; load all tuning values through `NovaConfig` instead of hardcoding
- 🔴 `30 March 2026` make hatch spawn pools data-driven from `hatch.toml`; move all rarity pools and creatures out of `eggs/data.py`

### code audits

- 🔴 `30 March 2026` audit for anything not properly using our systems: scheduler, config, db, commands, files organized correctly, etc
- 🔴 `30 March 2026` audit event-driven tasks and code; identify design improvements and best practices gaps
- 🔴 `30 March 2026` analyze the coverage report and audit what code we're missing and if it needs to have test cases
- 🔴 `30 March 2026` assess whether `NovaConfig` should be split into a sub-package with separate classes for guild, global, theme, hatch game, etc
- 🔴 `30 March 2026` audit starboard; learn from our mistakes to mould a better more fault tolerant, resilient system
- 🔴 `30 March 2026` check code for backwards compat interfaces, see which ones we can remove/refactor out
- 🔴 `30 March 2026` audit codebase for non-standard or inconsistent terminology and decide whether to standardize
- 🔴 `30 March 2026` investigate unifying stored date types under one class (`config.py:108`)

### maintenance

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

---

## coverage

| Stmts | Miss | Branch | BrPart | Cover |
|------:|-----:|-------:|-------:|------:|
| 8477 | 3147 | 2102 | 247 | 60% |

### attubot

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/__init__.py | 11 | 0 | 0 | 0 | 100% |
| attubot/config.py | 449 | 154 | 88 | 22 | 61% |
| attubot/logging.py | 43 | 7 | 0 | 0 | 84% |
| attubot/signals.py | 16 | 1 | 2 | 1 | 89% |

### attubot/client

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/client/__init__.py | 49 | 4 | 6 | 0 | 93% |
| attubot/client/calendar.py | 129 | 13 | 40 | 5 | 87% |
| attubot/client/core.py | 12 | 0 | 0 | 0 | 100% |
| attubot/client/embeds.py | 19 | 2 | 12 | 3 | 84% |
| attubot/client/events.py | 247 | 145 | 70 | 2 | 39% |
| attubot/client/families.py | 36 | 20 | 8 | 0 | 36% |
| attubot/client/logo.py | 18 | 2 | 2 | 1 | 85% |
| attubot/client/markers.py | 148 | 39 | 46 | 6 | 68% |
| attubot/client/messages.py | 323 | 115 | 118 | 18 | 60% |
| attubot/client/migrations.py | 266 | 266 | 56 | 0 | 0% |
| attubot/client/modlog.py | 325 | 62 | 142 | 40 | 77% |
| attubot/client/starboard.py | 563 | 162 | 222 | 44 | 69% |
| attubot/client/util.py | 56 | 12 | 10 | 1 | 71% |
| attubot/client/years.py | 74 | 0 | 16 | 0 | 100% |

### attubot/commands

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/commands/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/commands/chat.py | 151 | 120 | 40 | 0 | 16% |
| attubot/commands/debug.py | 208 | 136 | 36 | 0 | 30% |
| attubot/commands/eggs.py | 229 | 28 | 64 | 4 | 88% |
| attubot/commands/fix.py | 483 | 272 | 126 | 11 | 42% |
| attubot/commands/link.py | 110 | 79 | 12 | 0 | 25% |
| attubot/commands/marker.py | 82 | 53 | 16 | 0 | 30% |
| attubot/commands/query.py | 33 | 18 | 8 | 0 | 37% |
| attubot/commands/stars.py | 200 | 77 | 38 | 5 | 58% |
| attubot/commands/time.py | 43 | 24 | 4 | 0 | 40% |
| attubot/commands/wiki.py | 152 | 42 | 30 | 4 | 69% |
| attubot/commands/year.py | 89 | 8 | 34 | 4 | 90% |

### attubot/database

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/database/__init__.py | 68 | 4 | 0 | 0 | 94% |
| attubot/database/connection.py | 53 | 20 | 10 | 2 | 59% |
| attubot/database/models.py | 176 | 0 | 0 | 0 | 100% |
| attubot/database/repositories.py | 532 | 131 | 84 | 5 | 72% |

### attubot/eggs

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/eggs/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/eggs/data.py | 4 | 0 | 0 | 0 | 100% |
| attubot/eggs/emojis.py | 52 | 0 | 8 | 0 | 100% |
| attubot/eggs/hatching.py | 155 | 6 | 48 | 5 | 94% |

### attubot/ingestor

| Module | Stmts | Miss | Branch | BrPart | Cover |
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

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/tasks/__init__.py | 25 | 0 | 0 | 0 | 100% |
| attubot/tasks/base.py | 12 | 3 | 0 | 0 | 75% |
| attubot/tasks/chat_init.py | 31 | 18 | 0 | 0 | 42% |
| attubot/tasks/db_backup.py | 73 | 0 | 20 | 0 | 100% |
| attubot/tasks/egg_cleanup.py | 49 | 5 | 16 | 2 | 89% |
| attubot/tasks/error_hook.py | 44 | 26 | 8 | 0 | 35% |
| attubot/tasks/logo_update.py | 55 | 31 | 10 | 1 | 38% |
| attubot/tasks/message_backfill.py | 167 | 46 | 48 | 6 | 72% |
| attubot/tasks/nova_year.py | 122 | 49 | 40 | 1 | 57% |
| attubot/tasks/presence.py | 24 | 4 | 4 | 2 | 79% |
| attubot/tasks/reload_watcher.py | 53 | 3 | 16 | 2 | 93% |
| attubot/tasks/scheduler.py | 96 | 61 | 30 | 1 | 29% |

### attubot/web

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/web/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/web/app.py | 121 | 19 | 6 | 2 | 83% |
| attubot/web/audit.py | 75 | 21 | 20 | 3 | 68% |
| attubot/web/auth.py | 256 | 80 | 60 | 6 | 68% |
| attubot/web/discord_integration.py | 105 | 62 | 26 | 4 | 37% |
| attubot/web/forms.py | 185 | 15 | 62 | 6 | 87% |
| attubot/web/routes.py | 577 | 104 | 166 | 28 | 80% |

### attubot/wiki

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/wiki/__init__.py | 15 | 5 | 2 | 0 | 59% |
| attubot/wiki/admin.py | 23 | 0 | 2 | 0 | 100% |
| attubot/wiki/auth.py | 19 | 0 | 0 | 0 | 100% |
| attubot/wiki/client.py | 22 | 9 | 0 | 0 | 59% |
| attubot/wiki/models.py | 29 | 0 | 2 | 0 | 100% |
| attubot/wiki/pages.py | 70 | 56 | 12 | 0 | 17% |
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
last_updated: 31 March 2026
total_completed: 46
```
