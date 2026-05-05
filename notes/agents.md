# agents.md - AttuBot / Doom Bot

Guidance for AI coding agents working in this repository.

---

## project overview

**AttuBot** (repo name: `doom-bot`) is a Discord bot for the Attu Project that automates in-universe timekeeping, year-transition announcements, wiki management, and related utilities. It is written in **Python 3.13** and ships as a Docker container.

There are two runnable modes, both launched from `attu-bot.py`:

- `bot` - the Discord bot (pycord)
- `web` - a Quart-based admin web interface

---

## rules

1. do not edit the rules.
1. do not perform any interactions with Discord without asking.
1. do not create commits without being explicitly asked to; ask for confirmation immediately before running each `git commit`, even when already instructed to commit.
1. all noqa comments must include a valid reason
1. check the current time at the start of each conversation. if it is past 12:30 AM ET, suggest a natural stopping point before continuing any task.

## sub-agents

when operating as a sub-agent (spawned via the agent tool), assume other agents may be working concurrently in the same repository:

- **work off the `dev` branch** — the dev worktree lives at `/srv/services/doom-bot-dev`; when isolated in a worktree, ensure it is based on `dev`, not `trunk`
- do not run git operations that modify shared state (`checkout`, `reset`, `merge`, `rebase`, `stash`) unless isolated in a worktree
- do not assume exclusive access to any file or the working directory
- prefer additive changes; avoid deleting or overwriting files without checking for concurrent edits
- if isolated git work is needed, use a worktree (`EnterWorktree`) rather than modifying the main tree
- **do not run tests** — never invoke `pytest`, `docker compose run ... tests`, `npm test`, or any test runner; testing is the responsibility of the main agent only
- **do not run docker commands** — never invoke `docker`, `docker compose`, or any container tooling

---

## architecture

### entry point
- `attu-bot.py` - CLI dispatcher; selects `bot` or `web` mode via `sys.argv[1]`

### package: `attubot/`
| File | Role |
|---|---|
| `__init__.py` | Module metadata constants (`__version__`, `__build_time__`, etc.); re-exports `bot`, `config`, `db`, and startup functions from `attubot.client` |
| `config.py` | `NovaConfig` - three-stage config loader (`on_init` → `on_load` → `on_ready`); Pydantic models for all config sections |
| `signals.py` | Cross-process reload signaling via MongoDB; `send_signal()` writes a signal the bot picks up via `ReloadWatcherTask` |
| `logging.py` | Custom `Logger` class (termcolor-based); use `get_logger(__name__)` everywhere |

### package: `attubot/client/`
| File | Role |
|---|---|
| `__init__.py` | Startup pipeline - `start_bot_loop()`, `_check_deps()`, `_load_event_handlers()`, `_register_core_commands()`, `_load_extensions()`; auto-discovers `extensions_list` via `pkgutil`; `/ping` is registered here directly as an intentional exception to the extension pattern (lightweight core health check) |
| `core.py` | Module-level singletons: `bot` (Discord Bot), `config` (NovaConfig), `db` (MongoStorage) |
| `events.py` | Bot event handlers (`on_ready`, `on_message`, `on_member_join`, `on_application_command_error`, `before_invoke`); `_shutdown()` helper |
| `embeds.py` | `make_embed()` - standard embed builder with auto-theme color and timestamp; see the `pycord` skill (`embeds` section) |
| `markers.py` | `YearMarker` runtime model + bot extension setup |
| `years.py` | `Year` runtime model + bot extension setup |
| `calendar.py` | Pure calendar math - `get_year_status()`, `get_year_span()`, `get_next_year()` |
| `messages.py` | Message storage, `build_message_doc()`, edit/delete log embeds sent to the logs channel |
| `modlog.py` | Moderation log event handlers - member join/leave/ban, channel/role/emoji changes, nickname and timeout updates |
| `starboard.py` | Starboard reaction processing (`handle_star_add`, `handle_star_remove`), embed builder (`build_embeds`), post sync logic |
| `families.py` | FamilyEcho client - `is_family_file`, `get_viewer_url` (httpx POST), and family repo accessors |
| `logo.py` | Logo generation and SVG-to-PNG rendering via `resvg` |
| `migrations.py` | Schema migration table |
| `util.py` | Shared helpers - `theme_color()`, `format_message_link()`, `break_at_newline()`, permission checks |

### package: `attubot/database/`
| File | Role |
|---|---|
| `__init__.py` | `init_database()` - connects storage and seeds all module-level repo singletons |
| `connection.py` | `MongoStorage` singleton; `connect()`, `get_db()`, `close()` |
| `models.py` | Pydantic document models - `GuildConfigDocument`, `YearDocument`, `MessageDocument`, `StarredMessageDocument`, etc. |
| `repositories.py` | All async repository classes - `ConfigRepository`, `YearRepository`, `YearMarkerRepository`, `MessageRepository`, `StarboardRepository`, `ReloadSignalRepository` |

### package: `attubot/eggs/`
Egg collection mini-game.

| File | Role |
|---|---|
| `data.py` | rarity constants, hatch durations, drop weights, hatch pools |
| `emojis.py` | SVG→PNG rendering and Discord custom emoji upload (`ensure_egg_emojis`) |
| `hatching.py` | core game logic - `hatch_date()`, `collect_egg()`, `hatch_egg()`, `run_hatch_animation()`, `ensure_eggs_ready()` |

Slash commands live in `attubot/commands/eggs.py`. See [`notes/features/eggs.md`](notes/features/eggs.md) for behavior rules, storage schema, and setup instructions.

### package: `attubot/commands/`
Each file is a pycord extension (`setup(bot)` function) that registers a `SlashCommandGroup`.

| File | Slash Group | Purpose |
|---|---|---|
| `chat.py` | `/ask` | RAG lore assistant - embeds query, vector-searches Qdrant, reranks with CrossEncoder, streams LLM response; see `attubot/ingestor/` |
| `debug.py` | `/debug` | Diagnostic commands - version, scheduler state, year stats, message stats, starboard dump, config dump |
| `fix.py` | `/fix` | Repair/rebuild commands - logo refresh, year links rebuild, message backfill, starboard learn and recount |
| `marker.py` | `/marker` | Save, set, and clear year marker messages |
| `query.py` | `/query` | Channel pin queries |
| `stars.py` | `/stars` | Starboard browsing (`random`, `lost`, `recheck`) and leaderboards (`most-stars`, `most-starred`, `most-given`) |
| `time.py` | `/time` | In-universe time controls - advance, pause, resume, dilate |
| `wiki.py` | `/wiki` | Wiki lookup (`random`, `lookup`) and admin (`block`); uses `WikiLinkView` / `WikiLookupView` |
| `year.py` | `/year` | Year check, search, and link commands |
| `link.py` | `/link` | FamilyEcho family tree commands (`family list`, `family view`, `family set`, `family upload`) |
| `trees.py` | `/trees` | family tree editor link, show, share, and unshare commands |
| `eggs.py` | `/eggs` | Egg collection game - hatch, view, give, progress |
| `remind.py` | `/remind` | In-universe date reminders - add, list, cancel; fires when haracalnde date arrives |

### package: `attubot/ingestor/`
RAG ingestion pipeline for the `/ask` feature. Models are lazy singletons loaded by `ChatInitTask`. See [`notes/features/attu_chat.md`](notes/features/attu_chat.md) for full design and decisions.

| File | Role |
|---|---|
| `__init__.py` | `start_ingestor()` - creates TaskScheduler, registers tasks, starts internal Quart API |
| `embedder.py` | `Embedder` - wraps `all-MiniLM-L6-v2` sentence-transformers; `embed()` / `embed_batch()` |
| `reranker.py` | `Reranker` - CrossEncoder reranking; `rerank(query, candidates)` adds `rerank_score` to each result |
| `llm.py` | `LlmClient` - streaming llama.cpp HTTP client (OpenAI-compat); dual-URL primary/fallback |
| `vector_store.py` | `VectorStore` - Qdrant client wrapper; `search()`, `upsert()`, `delete()`; COSINE distance |
| `registry.py` | `ChatSourceRepository` access; tracks ingested content for deduplication |
| `query_expander.py` | expands user queries before embedding to improve recall |
| `summarizer.py` | summarizes long Discord threads before ingestion |
| `tasks.py` | `DiscordIngestTask`, `WikiIngestTask`, `SummarizationTask` (`BaseTask` subclasses) |
| `pipelines/wiki.py` | wiki page fetch → section split → embed → upsert |
| `pipelines/discord.py` | reply-chain graph traversal, time-window grouping, noise filtering |

Context blocks use `<article source="wiki" name="Page Title > Section">` tags. The system prompt is at `assets/prompts/chat-system-prompt.md`.

### package: `attubot/tasks/`
Background tasks managed by `TaskScheduler`. Each task extends `BaseTask` (`on_start`, `next_run`, `run`).

| File | Role |
|---|---|
| `base.py` | `BaseTask` ABC - defines the task lifecycle interface |
| `scheduler.py` | `TaskScheduler` - registers tasks, drives `_run_loop()` per task, exposes `running_tasks()` |
| `chat_init.py` | `ChatInitTask` - one-shot startup task; loads embedder, reranker, vector store, LLM client, and system prompt |
| `nova_year.py` | `NovaYearTask` - checks for year rollover on schedule; `job_construct_year_links()` helper |
| `message_backfill.py` | `MessageBackfillTask` - periodic scan of configured channels to store unseen messages |
| `logo_update.py` | `LogoUpdateTask` - refreshes the bot's avatar on a schedule |
| `db_backup.py` | `DatabaseBackupTask` - weekly mongodump to the configured backup path |
| `error_hook.py` | `ErrorHookTask` - periodic flush of queued webhook error notifications |
| `reload_watcher.py` | `ReloadWatcherTask` - polls MongoDB for reload signals sent from the web process |
| `presence.py` | `PresenceUpdateTask` - updates bot presence to reflect hatched egg count; 30-minute schedule, also triggered after each hatch |
| `egg_cleanup.py` | `EggCleanupTask` - deletes non-egg messages from egg threads on a configurable interval |
| `reminder.py` | `ReminderTask` - dynamic scheduling; delivers in-universe date reminders when haracalnde dates arrive |

### package: `attubot/wiki/`
| File | Role |
|---|---|
| `__init__.py` | `get_wiki()` singleton accessor; `setup(bot)` extension entry point |
| `client.py` | `WikiClient` - top-level client that composes auth, pages, search, and admin APIs |
| `auth.py` | `AuthApi` - login and CSRF token handling |
| `pages.py` | `PagesApi` - `get()`, `edit()`, `get_summary()`, `get_random_summary()` |
| `search.py` | `SearchApi` - full-text and title search, `site_info()` |
| `admin.py` | `AdminApi` - user block with retry logic |
| `models.py` | Pydantic models - `SearchResult`, `PageSummary`, `SiteInfo`, `PageThumbnail` |

### package: `attubot/web/`
Quart application with route registration, WebAuthn passkey auth, Discord OAuth integration, and an audit logger.

---

## configuration system (three tiers)

1. **`.env`** - only `ATTU_CONFIG_FILE`
2. **`assets/attu-bot.toml`** - secrets and static config (tokens, DB URL, wiki credentials, WebAuthn, authorized guilds). Copy from `config/attu-bot.sample.toml`.
3. **MongoDB** - runtime guild-level settings (epoch, channels, roles, users, theme)

`NovaConfig` loads in three stages - code that touches the DB or bot must wait for the appropriate stage (`on_init` / `on_load` / `on_ready`). Use the provided `wait_for_*` async methods if you need to gate on a stage.

### versioning

two independent version constants live in `attubot/__init__.py`:

- **`__schema__`** - db migration version; bumped for every migration in `client/migrations.py`. compared against the version stored in MongoDB (`global_config.system.version`) to decide whether to run migrations.
- **`__config_version__`** - minimum compatible TOML config file version; bumped only when the TOML file format changes (new sections, renamed keys, etc.). the TOML's `config_version` field is checked with `>=` against this value on startup.

db-only migrations bump `__schema__` only. TOML format changes bump both and update `config/attu-bot.sample.toml`. migration execution is handled by `run_pending_migrations()` in `client/migrations.py`; `NovaConfig` calls it at the appropriate lifecycle stage.

### adding a new config field

Pick the right tier first. Static secrets and startup values belong in the TOML; operator-adjustable per-guild values belong in MongoDB; nothing new belongs in `.env`.

**Tier 2 - TOML (`assets/attu-bot.toml`)**
- Add the field to the relevant Pydantic model in `config.py`
- Add it with a sensible placeholder value to `config/attu-bot.sample.toml`

**Tier 3 - MongoDB (guild-level)**

missing any of these steps causes the field to silently use its default in production regardless of what is in the database.

- `database/models.py` - add to `GuildConfigDocument` with a default; `extra='ignore'` means keys not listed here are never read from MongoDB
- `config.py` (`GuildConfig`) - add to the runtime model with the same default
- `config.py` (`NovaConfig.load_guild()`) - pass the value explicitly when constructing `GuildConfig` from the document; missing this causes the field to silently use its default in production
- `web/forms.py` (`GuildConfigForm`) - add the field so saves from the web UI don't silently drop it
- `assets/templates/guild_config.html` - add the form control
- `assets/static/js/app.js` (`loadGuildConfig()`) - add a `populateField('field_name', data.field_name)` call so the control reflects the saved value on load
- **roundtrip test** - save a document with the field set to a non-default value, reload via `load_guild()`, assert the value survives; this directly catches the hydration failure mode

**if the field gates an extension**
- in the task that auto-activates it: call `bot.reload_extension()` + `bot.sync_commands()` on the `False → True` transition
- in `tasks/reload_watcher.py`: diff old vs. new value after `config.load_guild()` and reload or unload the extension so web-triggered changes take effect without a restart

---

## coding conventions

### python style (enforced by `ruff`)
- **Target**: Python 3.13; use modern syntax freely
- **Formatter**: `ruff format` - single quotes, 4-space indentation
- **Linter**: `ruff check` with a broad rule set (E, F, Q, W, I, UP, ASYNC, S, A, COM, SIM, PTH, PL, RUF)
- **Line length**: 320 (effectively unlimited; do not wrap arbitrarily)
- **Quotes**: single quotes for inline strings, double quotes for docstrings
- **Imports**: stdlib → third-party → local; one blank line after each import block (isort)
- **Docstrings**: Google-style convention (`[tool.ruff.lint.pydocstyle]`)
- **Constants**: use regular lowercase names (`seconds_per_day`, not `SECONDS_PER_DAY`); screaming snake case is not used
- **Type annotations**: use modern union syntax (`X | Y`, `list[X]`, etc.); `from __future__ import annotations` is not needed under Python 3.13
- **Type checking**: basedpyright in `standard` mode; `typeCheckingMode = "standard"` (several optional-access rules are suppressed)
- **Forward type references**: keep as strings (`'ClassName'`) - `UP037` is ignored
- `wip/` and `*.wip.py` files are excluded from linting/type checking

### file header (required on every python file)
```python
"""
AttuBot - <Short Description>
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""
```

### logging
always use the custom logger - never the stdlib `logging` module directly:
```python
from attubot.logging import get_logger

logger = get_logger(__name__)
```
levels available: `trace`, `debug`, `info`, `warn`, `error`, `fatal`, `alert`. `trace`/`debug`/`alert` are no-ops unless `DEBUG` env var is set.

### pydantic
- All MongoDB documents extend `pydantic.BaseModel` and live in `models.py`
- Runtime domain models (e.g. `Year`, `YearMarker`, `GuildConfig`) also extend `pydantic.BaseModel` and wrap the document models
- Use `model_config = ConfigDict(extra='ignore')` on document models to tolerate schema evolution
- Validate config sections with `ValidationError` and re-raise as a domain error where appropriate

### async
- All I/O (Discord API, MongoDB) is async; use `asyncio.gather()` for parallel operations
- Bot extensions initialize synchronously inside `setup(bot)` by calling `loop.run_until_complete()`
- The web layer uses Quart (async Flask); route handlers are `async def`

### discord (pycord)
- Slash commands use `@discord.slash_command()` or `SlashCommandGroup`
- Each command module is a pycord **extension** with a `setup(bot: Bot)` function
- Options use `@discord.commands.option()` decorators
- permission checks: `from discord.ext import commands` then `@commands.check(predicate)`; `discord.commands` does NOT have `check` - it only exposes `option` and `SlashCommandGroup`; predicates live in `util.py` (`is_bot_owner`, `is_authorized_guild`, `has_announcements_role`)
- Error handling: `on_application_command_error` in `events.py` is the global handler - extension-level commands should raise naturally
- **ephemeral responses**: use `ephemeral=True` only for errors and validation failures; successful command responses should be public (no `ephemeral` argument)

### mongodb / repository pattern
- All database access goes through the repository classes in `repositories.py`
- Repositories are instantiated lazily via module-level `_get_repo()` helpers
- Use `upsert=True` (`$set`) for saves; never assume a document exists
- Index creation happens in `init_indexes()` on each repository; call this at extension load time
- Discord snowflake IDs are stored as `int` in MongoDB

### web (quart)
- all routes are registered in `routes.py` via `register_routes(app: Quart)`
- API routes return `jsonify(...)` with standard shapes: `{'error': '...'}` on failure, `{'success': True, 'message': '...'}` on success
- Discord IDs in JSON responses are serialized as **strings** to avoid JavaScript precision loss
- Validation uses Pydantic form models from `web/forms.py`; return `400` with `e.errors()` on `ValidationError`
- mutations go through the audit logger (`web_app.audit_logger.log_change(...)`)

### javascript
- ES modules (`"type": "module"` in `package.json`)
- Linted with ESLint 10; run `npm run lint`
- Tested with Vitest; test files follow `*.test.js` naming
- no transpilation - targets the runtime directly

---

## testing
```
docker compose run --build --rm --quiet-build tests
```

- `asyncio_mode = "auto"` - async tests work without explicit `@pytest.mark.asyncio`
- All tests run with `TZ=UTC`; uses **freezegun** for deterministic calendar calculations
- Fixture table and test constants: see [`notes/dev/testing.md`](notes/dev/testing.md)

**mock compensation rule:** when a test mocks a framework mechanism, it inherits responsibility for the behavior that mock hides. canonical reference and standing cases (extension loading, permission checks, migrations) are in the `mock-compensation` skill.

### linting
```bash
ruff check .           # Python lint
ruff format --check .  # Python format check
npm run lint           # JS lint
```
---

## running locally

```bash
docker compose up --build -d
docker compose logs -f
```

See [`notes/dev/dev_setup.md`](notes/dev/dev_setup.md) for the full dev worktree workflow, seed refresh, and deployment steps.

---

## feature completion checklist

the canonical end-of-task checklist (tests, documentation, configuration plumbing, web interface, linting) is the `feature-completion` skill. the skill auto-loads on wrap-up signals (`pytest`, `ruff check`, "ready to commit", drafting a `git commit` message) and is canonical - if it diverges from this file, the skill wins and this section gets updated to match.

---

## important patterns & pitfalls

- **`TEST_MODE` env var**: when set, the bot exits cleanly after reaching ready state without a 60-second restart delay. migrations are also skipped.
- **`DEBUG` env var**: enables `trace`/`debug`/`alert` log levels.
- **config singleton**: `bot`, `config`, and `db` singletons are defined in `attubot/client/core.py` and re-exported from `attubot`. extensions can import them from either path.
- **guild authorization**: always check `guild_id in config.authorized_guilds` before acting. `config.guild(id)` raises `UnauthorizedGuild` for unknown guilds.
- **snowflake precision**: Discord IDs exceed JavaScript's safe integer range - serialize them as strings in any JSON API response.
- **rollover time storage**: stored as `rollover_minutes` (int, minutes since midnight) in MongoDB; the legacy string format (`"17:00"`) is handled by a `model_validator` in `GuildEpoch`.
- **`wip/` directory**: excluded from all linting and type checks; use it for exploratory/in-progress work.
- **`resvg` dependency**: the bot checks for `/usr/local/bin/resvg` at startup and exits if missing - it is bundled in the Docker image.
- **error webhook**: unhandled exceptions in commands are forwarded to a Discord webhook via `logger.send_to_webhook(err)`.
- **permission checks on slash commands**: use `@commands.check(predicate)` from `discord.ext.commands` - NOT `@discord.commands.check()`, which does not exist in pycord. all command modules use `from discord.ext import commands`.

---

## reference notes

Notes in `notes/` with relevant implementation details:

**`notes/style/`** - deeper api references; project-specific style rules now live in skills (see below)
- [`embed_usage.md`](notes/style/embed_usage.md) - `discord.Embed` deep api reference (chainable setters, accessors, dict roundtrip, fields you can't set); project rules in the `pycord` skill
- [`button_usage.md`](notes/style/button_usage.md) - `discord.ui` deep api reference (decorator vs `add_item`, button styles, action rows, persistent views, modals/selects); project patterns in the `pycord` skill

**`notes/features/`** - feature specs and system docs
- [`eggs.md`](notes/features/eggs.md) - egg game behavior rules, storage schema, key functions, commands, and setup
- [`starboard.md`](notes/features/starboard.md) - starboard feature spec and embed structure reference
- [`markers.md`](notes/features/markers.md) - marker system spec (resolution order, storage, commands, web API)
- [`timekeeping.md`](notes/features/timekeeping.md) - in-universe calendar system, epoch math, year spans, rollover
- [`reminders.md`](notes/features/reminders.md) - in-universe date reminders, fire time computation, storage, commands
- [`tasks.md`](notes/features/tasks.md) - task scheduler overview, BaseTask lifecycle, naming scheme, and how to add tasks
- [`web.md`](notes/features/web.md) - web interface structure, routes, auth, signals, audit logging, and how to extend it
- [`attu_chat.md`](notes/features/attu_chat.md) - chat/RAG system full architecture and design decisions

**`notes/dev/`** - development guides
- [`testing.md`](notes/dev/testing.md) - test layout, fixtures, conventions (mock compensation rule moved to its skill)
- [`dev_setup.md`](notes/dev/dev_setup.md) - dev worktree setup, running tests, deploying to prod

**`notes/`**
- [`to-do.md`](notes/to-do.md) - active project to-do list, test coverage table, and completed task history
- [`.meta.md`](.meta.md) - guide for recreating this agents.md and notes/ system in another repository

## skills

prescriptive, auto-loaded reference cards live in `.claude/skills/`. each loads when its trigger condition matches the current task; treat each as canonical for the rule it codifies.

| skill | covers | triggers on |
|---|---|---|
| `commit-style` | commit format, types, scope, what belongs in one commit | drafting commit messages; `git commit` / `git status` / `git diff` |
| `comment-style` | python comment case/punctuation, section dividers, todo tags, noqa reasons | any python edit |
| `message-style` | log tone, discord response voice, error format (`Failed:`), custom emojis, ephemeral rule | edits in `commands/` / `client/` / `tasks/` / `web/`; `logger.*`; `ctx.respond` / `interaction.response` |
| `feature-completion` | end-of-task checklist (tests, docs, config plumbing, web, lint) | wrap-up signals; `pytest`, `ruff`, drafting a commit |
| `mock-compensation` | the mock compensation rule and three standing cases | edits in `tests/python/`; new files in `commands/`; new predicates; new migrations |
| `pycord` | py-cord 2.x reference, the `commands` modules split, extensions, slash commands, embeds, views | `attubot/commands/` / `attubot/client/`; imports of `discord.*` |
| `pydantic` | pydantic v2 idioms, document/runtime split, six-step tier-3 plumbing checklist | `database/models.py`, `config.py`, `web/forms.py`; `pydantic` imports |
| `mediawiki-api` | mediawiki action api + mwparserfromhell reference | `attubot/wiki/`; `ingestor/pipelines/wiki.py`; `commands/wiki.py` |
| `ferretdb-quirks` | ferretdb v2 + documentdb postgres divergences from real mongo | `attubot/database/`; `migrations.py`; `scripts/ferret_init.sh` |

---

## file & directory layout

```
attu-bot.py              # entrypoint
attubot/                 # main package
  client/                # discord-specific runtime (singletons, events, features)
  commands/              # slash command extensions (one group per file)
  database/              # mongodb connection, models, and repositories
  tasks/                 # background task scheduler and task implementations
  web/                   # Quart web app
  wiki/                  # mediawiki api client
assets/                  # runtime assets (TOML config, templates, static)
config/                  # sample/reference config files (not used at runtime)
tests/                   # pytest + vitest test suites
scripts/                 # utility scripts (backup, migration, test runner)
notes/                   # project notes (not code); subdirs: style/, features/, dev/
wip/                     # work-in-progress scratch space (excluded from lint)
```

# personality

- use semicolons or regular dashes (-); never em-dashes
  - semicolon: joins two independent clauses or a cause and consequence (`"migration failed; refusing to continue"`)
  - dash: trailing aside, parenthetical, or annotation (`"lazy singleton initialization requires global"` in a noqa comment)
- do not include any extraneous punctuation
- write code comments in all lowercase including at the beginning of sentences, except where it would be unclear; prefer to be brief
- use american english spelling and grammar
- use spaces for indentation always; avoid formats that require tabs
- prefer brief statements over long explanations

---

## metadata

```yaml
last_updated: 3 April 2026 (sub-agents section added)
```
