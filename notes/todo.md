# to-do

## egg related

- [2] effort: medium - make sure tests cases cover all aspects of the hatch system
- [2] effort: medium - task to clean up all the non-egg messages (like older than 12h) in the egg threads

## starboard

- [2] effort: medium - add a /stars command to show which starboard messages have the most stars (not users)
- [2] effort: medium - /stars leaderboard results should be paginated with the same buttons as the wiki results.
- [2] effort: medium - add optional filters to /stars random and /stars lost for like user, and min stars for random, which emoji (might have to be by name)
- [2] effort: high - stickers, voice memos still have rendering issues. with the latter not showing the no preview text bit either. the gif links aren't showing right either, they include a png instead of the gif/gifv.
- [3] effort: high - audit starboard and refactor into less of a mess

## wiki

- [2] effort: medium - add optional filters to /wiki random to restrict to pages within a category
- [3] effort: medium - add where you can cycle through the different sections on the page (up and down arrows maybe?)

## moderation / logging

- [2] effort: medium - add kick, ban, and timeout commands

## web interface

- [2] effort: medium - fix everywhere we're currently displaying raw snowflakes for
- [3] effort: medium - primary / secondary guild toggle instead of having all guilds

## maintenance

- [3] effort: low - add progress bars to run_tests.py
- [3] effort: low - check for spelling across all notes / code
- [2] effort: medium - analyze the coverage report below, then audit what code we're missing and if it needs to have test cases
- [2] effort: medium - audit command descriptions and make sure they make sense, match style guide, only say needed/user-facing details; add completions; improve interface, add embeds where it makes sense
- [2] effort: medium - we use hard-coded custom emojis in a lot of the responses; centralize this into one place; already storing some emoji ids with the theme
- [2] effort: high - audit for anything not properly using our systems: scheduler, config, db, commands, files organized correctly, etc
- [3] effort: high - check code for backwards compat interfaces, see which ones we can remove/refactor out

## recurring

- [2] effort: low - repeatable: assign any to-dos without an effort or category; update priorities; move completed and sort all
- [2] effort: low - repeatable: run docker tests with --coverage flag; update coverage in second section; update testing to-dos with gaps
- [3] effort: medium - repeatable: add more stats to web interface
- [3] effort: medium - repeatable: update docs, notes, and readme; reorganize and consolidate notes

## future

- [4] effort: high - refactor out ferret and just use postgres + documentdb?

## testing

- [2] effort: low - add tests for eggs/emojis.py (52%) - emoji fetch and validation helpers
- [3] effort: low - add tests for client/families.py (36%) and database/connection.py (59%)
- [2] effort: medium - add tests for tasks/scheduler.py (29% coverage) - task scheduling, cancellation, restart logic
- [2] effort: medium - add tests for commands/link.py (25%) and commands/marker.py (30%)
- [2] effort: medium - add tests for commands/debug.py (30%) and commands/time.py (40%)
- [2] effort: medium - add tests for tasks/logo_update.py (38%) and tasks/error_hook.py (35%)
- [2] effort: medium - add tests for tasks/hatching.py (41%) and tasks/nova_year.py (57%)
- [3] effort: medium - add tests for wiki/pages.py (17% coverage) - page fetch and parsing
- [3] effort: medium - add tests for web/discord_integration.py (37% coverage)
- [3] effort: medium - add tests for commands/query.py (37%) and commands/stars.py (58%)
- [2] effort: high - add tests for commands/fix.py (42% coverage, 495 stmts) - focus on reconcile, starboard, and emoji fix subcommands
- [2] effort: high - add tests for commands/chat.py (16% coverage) - slash command dispatch and response logic
- [2] effort: high - add tests for ingestor pipeline modules (discord.py and wiki.py at 0% coverage)
- [2] effort: high - add tests for client/events.py (39% coverage) - on_ready, on_message, on_application_command_error handlers
- [2] effort: high - add tests for client/messages.py (60% coverage) - build_message_doc, edit/delete log embeds
- [3] effort: high - add tests for ingestor/summarizer.py (0%) and ingestor/llm.py (21%)

---

# completed

## egg related

- [x] combine all the /fix emoji commands into one that just double-checks everything
- [x] refactor all custom emojis into a single place, and have all be configurable
- [x] move the emoji images all into the /assets/static/emoji/ folder along with egg.svg. credit https://emoji.gg/pack/7783-progress-bar# in the readme somewhere. update the code where needed.
- [x] unignore eggs.md
- [x] egg.svg is from google emojis. can we upload that to git according to its licensing? move to better path name too.
- [x] eggs command is in the eggs package and not in commands/eggs.py
- [x] add bot status message, egg related like "x eggs hatched" with the total number.
- [x] update sample config file to latest changes
- [x] audit eggs system for any bugs
- [x] egg trading? best way to implement?
- [x] /eggs progress: shows progress for each rarity. total and per rarity with progress bar and count.
- [x] progress bar emojis: upload to secondary server, store in config, expose via /fix emoji progress.

## wiki

- [x] wiki result messages with the buttons: not removed on disable, not preserved through reboots - store actions on message object

## maintenance

- [x] separate out the bot logo update task, run every 2.5 minutes; store hsl natively instead of hex
- [x] invert notes/ gitignore; we can explicitly ignore the ones we don't want

---

# coverage

## attubot

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/__init__.py | 11 | 0 | 0 | 0 | 100% |
| attubot/config.py | 448 | 154 | 88 | 22 | 61% |
| attubot/logging.py | 43 | 7 | 0 | 0 | 84% |
| attubot/signals.py | 16 | 1 | 2 | 1 | 89% |

## attubot/client

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/client/__init__.py | 49 | 4 | 6 | 0 | 93% |
| attubot/client/calendar.py | 129 | 13 | 40 | 5 | 87% |
| attubot/client/core.py | 12 | 0 | 0 | 0 | 100% |
| attubot/client/embeds.py | 19 | 2 | 12 | 3 | 84% |
| attubot/client/events.py | 245 | 144 | 70 | 2 | 39% |
| attubot/client/families.py | 36 | 20 | 8 | 0 | 36% |
| attubot/client/logo.py | 18 | 2 | 2 | 1 | 85% |
| attubot/client/markers.py | 148 | 39 | 46 | 6 | 68% |
| attubot/client/messages.py | 323 | 115 | 118 | 18 | 60% |
| attubot/client/migrations.py | 266 | 266 | 56 | 0 | 0% |
| attubot/client/modlog.py | 325 | 62 | 142 | 40 | 77% |
| attubot/client/starboard.py | 563 | 162 | 222 | 44 | 69% |
| attubot/client/util.py | 56 | 12 | 10 | 1 | 71% |
| attubot/client/years.py | 74 | 0 | 16 | 0 | 100% |

## attubot/commands

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/commands/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/commands/chat.py | 151 | 120 | 40 | 0 | 16% |
| attubot/commands/debug.py | 208 | 136 | 36 | 0 | 30% |
| attubot/commands/eggs.py | 214 | 34 | 60 | 4 | 84% |
| attubot/commands/fix.py | 483 | 272 | 126 | 11 | 42% |
| attubot/commands/link.py | 110 | 79 | 12 | 0 | 25% |
| attubot/commands/marker.py | 82 | 53 | 16 | 0 | 30% |
| attubot/commands/query.py | 33 | 18 | 8 | 0 | 37% |
| attubot/commands/stars.py | 200 | 77 | 38 | 5 | 58% |
| attubot/commands/time.py | 43 | 24 | 4 | 0 | 40% |
| attubot/commands/wiki.py | 152 | 42 | 30 | 4 | 69% |
| attubot/commands/year.py | 89 | 8 | 34 | 4 | 90% |

## attubot/database

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/database/__init__.py | 66 | 4 | 0 | 0 | 94% |
| attubot/database/connection.py | 53 | 20 | 10 | 2 | 59% |
| attubot/database/models.py | 176 | 0 | 0 | 0 | 100% |
| attubot/database/repositories.py | 517 | 119 | 82 | 5 | 74% |

## attubot/eggs

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/eggs/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/eggs/data.py | 4 | 0 | 0 | 0 | 100% |
| attubot/eggs/emojis.py | 52 | 25 | 8 | 0 | 52% |
| attubot/eggs/hatching.py | 155 | 11 | 48 | 9 | 89% |

## attubot/ingestor

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

## attubot/tasks

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/tasks/__init__.py | 23 | 0 | 0 | 0 | 100% |
| attubot/tasks/base.py | 12 | 3 | 0 | 0 | 75% |
| attubot/tasks/chat_init.py | 31 | 18 | 0 | 0 | 42% |
| attubot/tasks/db_backup.py | 73 | 0 | 20 | 0 | 100% |
| attubot/tasks/error_hook.py | 44 | 26 | 8 | 0 | 35% |
| attubot/tasks/hatching.py | 30 | 16 | 4 | 0 | 41% |
| attubot/tasks/logo_update.py | 55 | 31 | 10 | 1 | 38% |
| attubot/tasks/message_backfill.py | 167 | 46 | 48 | 6 | 72% |
| attubot/tasks/nova_year.py | 122 | 49 | 40 | 1 | 57% |
| attubot/tasks/presence.py | 24 | 4 | 4 | 2 | 79% |
| attubot/tasks/reload_watcher.py | 53 | 3 | 16 | 2 | 93% |
| attubot/tasks/scheduler.py | 96 | 61 | 30 | 1 | 29% |

## attubot/web

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/web/__init__.py | 0 | 0 | 0 | 0 | 100% |
| attubot/web/app.py | 121 | 19 | 6 | 2 | 83% |
| attubot/web/audit.py | 75 | 21 | 20 | 3 | 68% |
| attubot/web/auth.py | 256 | 80 | 60 | 6 | 68% |
| attubot/web/discord_integration.py | 105 | 62 | 26 | 4 | 37% |
| attubot/web/forms.py | 185 | 15 | 62 | 6 | 87% |
| attubot/web/routes.py | 570 | 101 | 164 | 27 | 80% |

## attubot/wiki

| Module | Stmts | Miss | Branch | BrPart | Cover |
|--------|------:|-----:|-------:|-------:|------:|
| attubot/wiki/__init__.py | 15 | 5 | 2 | 0 | 59% |
| attubot/wiki/admin.py | 23 | 0 | 2 | 0 | 100% |
| attubot/wiki/auth.py | 19 | 0 | 0 | 0 | 100% |
| attubot/wiki/client.py | 22 | 9 | 0 | 0 | 59% |
| attubot/wiki/models.py | 29 | 0 | 2 | 0 | 100% |
| attubot/wiki/pages.py | 70 | 56 | 12 | 0 | 17% |
| attubot/wiki/search.py | 29 | 0 | 0 | 0 | 100% |

### total

| Stmts | Miss | Branch | BrPart | Cover |
|------:|-----:|-------:|-------:|------:|
| 8386 | 3177 | 2078 | 248 | 59% |
