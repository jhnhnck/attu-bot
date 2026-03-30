# to-do

_see the [meta](#meta) section at the end of this file for format reference._

---

## tasks

### meta

- `medium priority` `low effort` assign any to-dos without an effort or category; update priorities; move completed and sort all
- `medium priority` `low effort` run docker tests with --coverage flag; update coverage in second section; update testing to-dos with gaps
- `low priority` `medium effort` add more stats to web interface
- `low priority` `medium effort` update docs, notes, and readme; reorganize and consolidate notes
- `low priority` `low effort` scan for files over ~300 lines; add to-do items for any that should be split up

### eggs

- ⭕ `medium priority` `low effort` split /eggs leaderboard into two separate commands: one for most hatched total, one for most complete set
- ⭕ `high priority` `low effort` deploy script doesn't ff trunk to the current tag, so nothing actually gets pushed; fix the ff step in deploy.py

### hatch

- ⭕ `future idea` `high effort` slight rebrand of the game into "hatch!"
- ⭕ `medium priority` `medium effort` create `eggs.toml` for egg game tuning; load hatch durations, drop weights, collect cooldown, animation wait range, cleanup interval and cutoff from it instead of hardcoding in `eggs/data.py`, `eggs/hatching.py`, and `tasks/egg_cleanup.py`
- ⭕ `medium priority` `medium effort` make hatch spawn pools data-driven from `eggs.toml`; move all rarity pools and the rarities list out of `eggs/data.py` so creatures can be added or removed without code changes

### starboard

- ⭕ `medium priority` `medium effort` add a /stars command to show which starboard messages have the most stars (not users)
- ⭕ `medium priority` `medium effort` /stars leaderboard results should be paginated with the same buttons as the wiki results.
- ⭕ `medium priority` `medium effort` add optional filters to /stars random and /stars lost for like user, and min stars for random, which emoji (might have to be by name)
- ⭕ `medium priority` `high effort` stickers, voice memos still have rendering issues. with the latter not showing the no preview text bit either. the gif links aren't showing right either, they include a png instead of the gif/gifv.
- ⭕ `low priority` `high effort` audit starboard; learn from our mistakes to mould a better more fault tolerant, resillent system

### wiki

- ⭕ `medium priority` `medium effort` add optional filters to /wiki random to restrict to pages within a category
- ⭕ `low priority` `medium effort` add where you can cycle through the different sections on the page (up and down arrows maybe?)

### moderation / logging

- ⭕ `medium priority` `medium effort` add kick, ban, and timeout commands

### web interface

- ⭕ `medium priority` `medium effort` fix everywhere we're currently displaying raw snowflakes for
- ⭕ `medium priority` `medium effort` web audit log should be enforced, not optional - currently guarded by `if web_app.audit_logger:` which silently skips auditing if not configured
- ⭕ `low priority` `medium effort` primary / secondary guild toggle instead of having all guilds

### maintenance

- ⭕ `medium priority` `medium effort` analyze the coverage report below, then audit what code we're missing and if it needs to have test cases
- ⭕ `medium priority` `medium effort` audit command descriptions and make sure they make sense, match style guide, only say needed/user-facing details; add completions; improve interface, add embeds where it makes sense
- ⭕ `medium priority` `medium effort` we use hard-coded custom emojis in a lot of the responses; centralize this into one place; already storing some emoji ids with the theme
- ⭕ `medium priority` `high effort` audit for anything not properly using our systems: scheduler, config, db, commands, files organized correctly, etc
- ⭕ `medium priority` `high effort` audit event-driven tasks and code; identify design improvements and best practices gaps
- ⭕ `low priority` `medium effort` update run_tests.py to match the polish of deploy.py - better output, progress bars, clear pass/fail summary
- ⭕ `low priority` `low effort` add progress bars to run_tests.py
- ⭕ `low priority` `low effort` change backfill task to debug logging; report start and end only
- ⭕ `low priority` `low effort` check for spelling across all notes / code
- ⭕ `low priority` `medium effort` deploy.py --revert option; takes a version tag, resets trunk to that commit, and rebuilds containers
- ⭕ `low priority` `high effort` check code for backwards compat interfaces, see which ones we can remove/refactor out
- ⭕ `future idea` `very high effort` refactor out ferret and just use postgres + documentdb?

### testing

- ⭕ `medium priority` `medium effort` add tests for tasks/scheduler.py (29% coverage) - task scheduling, cancellation, restart logic
- ⭕ `medium priority` `medium effort` add tests for commands/link.py (25%) and commands/marker.py (30%)
- ⭕ `medium priority` `medium effort` add tests for commands/debug.py (30%) and commands/time.py (40%)
- ⭕ `medium priority` `medium effort` add tests for tasks/logo_update.py (38%) and tasks/error_hook.py (35%)
- ⭕ `medium priority` `medium effort` add tests for tasks/nova_year.py (57%)
- ⭕ `medium priority` `high effort` add tests for commands/fix.py (42% coverage, 483 stmts) - focus on reconcile, starboard, and emoji fix subcommands
- ⭕ `medium priority` `high effort` add tests for commands/chat.py (16% coverage) - slash command dispatch and response logic
- ⭕ `medium priority` `high effort` add tests for ingestor pipeline modules (discord.py and wiki.py at 0% coverage)
- ⭕ `medium priority` `high effort` add tests for client/events.py (39% coverage) - on_ready, on_message, on_application_command_error handlers
- ⭕ `medium priority` `high effort` add tests for client/messages.py (60% coverage) - build_message_doc, edit/delete log embeds
- ⭕ `low priority` `low effort` add tests for client/families.py (36%) and database/connection.py (59%)
- ⭕ `low priority` `medium effort` add tests for wiki/pages.py (17% coverage) - page fetch and parsing
- ⭕ `low priority` `medium effort` add tests for web/discord_integration.py (37% coverage)
- ⭕ `low priority` `medium effort` add tests for commands/query.py (37%) and commands/stars.py (58%)
- ⭕ `low priority` `high effort` add tests for ingestor/summarizer.py (0%) and ingestor/llm.py (21%)

---

## completed tasks

### egg related

- 🔴 eggs leaderboard for most complete hatched set and most hatched total
- 🔴 task to clean up non-egg messages in the egg threads
- 🔴 refactor all custom emojis into a single place, and have all be configurable

### maintenance

- 🔴 deploy script (scripts/deploy.py)

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
| attubot/tasks/hatching.py | 28 | 1 | 4 | 0 | 97% |
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
last_updated: 30 March 2026
total_completed: 25
```
