# AGENTS.md - AttuBot / Doom Bot

Guidance for AI coding agents working in this repository.

---

## Project Overview

**AttuBot** (repo name: `doom-bot`) is a Discord bot for the Attu Project that automates in-universe timekeeping, year-transition announcements, wiki management, and related utilities. It is written in **Python 3.13** and ships as a Docker container.

There are two runnable modes, both launched from `attu-bot.py`:

- `bot` - the Discord bot (pycord)
- `web` - a Quart-based admin web interface

---

## Rules

1. Do not edit the rules.
1. Do not perform any interactions with Discord without asking.
1. All noqa comments must include a valid reason


## Architecture

### Entry Point
- `attu-bot.py` - CLI dispatcher; selects `bot` or `web` mode via `sys.argv[1]`

### Package: `attubot/`
| File | Role |
|---|---|
| `__init__.py` | Module metadata constants (`__version__`, `__build_time__`, etc.); re-exports `bot`, `config`, `db`, and startup functions from `attubot.client` |
| `config.py` | `NovaConfig` - three-stage config loader (`on_init` → `on_load` → `on_ready`); Pydantic models for all config sections |
| `signals.py` | Cross-process reload signaling via MongoDB; `send_signal()` writes a signal the bot picks up via `ReloadWatcherTask` |
| `logging.py` | Custom `Logger` class (termcolor-based); use `get_logger(__name__)` everywhere |

### Package: `attubot/client/`
| File | Role |
|---|---|
| `__init__.py` | Startup pipeline - `start_bot_loop()`, `_check_deps()`, `_load_event_handlers()`, `_register_core_commands()`, `_load_extensions()`; auto-discovers `extensions_list` via `pkgutil` |
| `core.py` | Module-level singletons: `bot` (Discord Bot), `config` (NovaConfig), `db` (MongoStorage) |
| `events.py` | Bot event handlers (`on_ready`, `on_message`, `on_member_join`, `on_application_command_error`, `before_invoke`); `_shutdown()` helper |
| `embeds.py` | `make_embed()` - standard embed builder with auto-theme color and timestamp; see `notes/embed_usage.md` |
| `markers.py` | `YearMarker` runtime model + bot extension setup |
| `years.py` | `Year` runtime model + bot extension setup |
| `calendar.py` | Pure calendar math - `get_year_status()`, `get_year_span()`, `get_next_year()` |
| `messages.py` | Message storage, `build_message_doc()`, edit/delete log embeds sent to the logs channel |
| `modlog.py` | Moderation log event handlers - member join/leave/ban, channel/role/emoji changes, nickname and timeout updates |
| `starboard.py` | Starboard reaction processing (`handle_star_add`, `handle_star_remove`), embed builder (`build_embeds`), post sync logic |
| `families.py` | Guild family grouping runtime model and helpers |
| `logo.py` | Logo generation and SVG-to-PNG rendering via `resvg` |
| `migrations.py` | Schema migration table |
| `util.py` | Shared helpers - `theme_color()`, `format_message_link()`, `break_at_newline()`, permission checks |

### Package: `attubot/database/`
| File | Role |
|---|---|
| `__init__.py` | `init_database()` - connects storage and seeds all module-level repo singletons |
| `connection.py` | `MongoStorage` singleton; `connect()`, `get_db()`, `close()` |
| `models.py` | Pydantic document models - `GuildConfigDocument`, `YearDocument`, `MessageDocument`, `StarredMessageDocument`, etc. |
| `repositories.py` | All async repository classes - `ConfigRepository`, `YearRepository`, `YearMarkerRepository`, `MessageRepository`, `StarboardRepository`, `ReloadSignalRepository` |

### Package: `attubot/commands/`
Each file is a pycord extension (`setup(bot)` function) that registers a `SlashCommandGroup`.

| File | Slash Group | Purpose |
|---|---|---|
| `debug.py` | `/debug` | Diagnostic commands - version, scheduler state, year stats, message stats, starboard dump, config dump |
| `fix.py` | `/fix` | Repair/rebuild commands - logo refresh, year links rebuild, message backfill, starboard learn and recount |
| `marker.py` | `/marker` | Save, set, and clear year marker messages |
| `query.py` | `/query` | Channel pin queries |
| `stars.py` | `/stars` | Starboard browsing (`random`, `lost`, `recheck`) and leaderboards (`most-stars`, `most-starred`, `most-given`) |
| `time.py` | `/time` | In-universe time controls - advance, pause, resume, dilate |
| `wiki.py` | `/wiki` | Wiki lookup (`random`, `lookup`) and admin (`block`); uses `WikiLinkView` / `WikiLookupView` |
| `year.py` | `/year` | Year check, search, and link commands |

### Package: `attubot/tasks/`
Background tasks managed by `TaskScheduler`. Each task extends `BaseTask` (`on_start`, `next_run`, `run`).

| File | Role |
|---|---|
| `base.py` | `BaseTask` ABC - defines the task lifecycle interface |
| `scheduler.py` | `TaskScheduler` - registers tasks, drives `_run_loop()` per task, exposes `running_tasks()` |
| `nova_year.py` | `NovaYearTask` - checks for year rollover on schedule; `job_construct_year_links()` helper |
| `message_backfill.py` | `MessageBackfillTask` - periodic scan of configured channels to store unseen messages |
| `logo_update.py` | `LogoUpdateTask` - refreshes the bot's avatar on a schedule |
| `db_backup.py` | `DatabaseBackupTask` - weekly mongodump to the configured backup path |
| `error_hook.py` | `ErrorHookTask` - periodic flush of queued webhook error notifications |
| `reload_watcher.py` | `ReloadWatcherTask` - polls MongoDB for reload signals sent from the web process |

### Package: `attubot/wiki/`
| File | Role |
|---|---|
| `__init__.py` | `get_wiki()` singleton accessor; `setup(bot)` extension entry point |
| `client.py` | `WikiClient` - top-level client that composes auth, pages, search, and admin APIs |
| `auth.py` | `AuthApi` - login and CSRF token handling |
| `pages.py` | `PagesApi` - `get()`, `edit()`, `get_summary()`, `get_random_summary()` |
| `search.py` | `SearchApi` - full-text and title search, `site_info()` |
| `admin.py` | `AdminApi` - user block with retry logic |
| `models.py` | Pydantic models - `SearchResult`, `PageSummary`, `SiteInfo`, `PageThumbnail` |

### Package: `attubot/web/`
Quart application with route registration, WebAuthn passkey auth, Discord OAuth integration, and an audit logger.

---

## Configuration System (Three Tiers)

1. **`.env`** - only `ATTU_CONFIG_FILE`
2. **`assets/attu-bot.toml`** - secrets and static config (tokens, DB URL, wiki credentials, WebAuthn, authorized guilds). Copy from `config/attu-bot.sample.toml`.
3. **MongoDB** - runtime guild-level settings (epoch, channels, roles, users, theme)

`NovaConfig` loads in three stages - code that touches the DB or bot must wait for the appropriate stage (`on_init` / `on_load` / `on_ready`). Use the provided `wait_for_*` async methods if you need to gate on a stage.

---

## Coding Conventions

### Python Style (enforced by `ruff`)
- **Target**: Python 3.13; use modern syntax freely
- **Formatter**: `ruff format` - single quotes, 4-space indentation
- **Linter**: `ruff check` with a broad rule set (E, F, Q, W, I, UP, ASYNC, S, A, COM, SIM, PTH, PL, RUF)
- **Line length**: 320 (effectively unlimited; do not wrap arbitrarily)
- **Quotes**: single quotes for inline strings, double quotes for docstrings
- **Imports**: stdlib → third-party → local; one blank line after each import block (isort)
- **Docstrings**: Google-style convention (`[tool.ruff.lint.pydocstyle]`)
- **Type annotations**: use modern union syntax (`X | Y`, `list[X]`, etc.); `from __future__ import annotations` is not needed under Python 3.13
- **Type checking**: basedpyright in `standard` mode; `typeCheckingMode = "standard"` (several optional-access rules are suppressed)
- **Forward type references**: keep as strings (`'ClassName'`) - `UP037` is ignored
- `wip/` and `*.wip.py` files are excluded from linting/type checking

### File Header (required on every Python file)
```python
"""
AttuBot - <Short Description>
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""
```

### Logging
Always use the custom logger - never the stdlib `logging` module directly:
```python
from attubot.logging import get_logger
logger = get_logger(__name__)
```
Levels available: `trace`, `debug`, `info`, `warn`, `error`, `fatal`. `trace`/`debug`/`alert` are no-ops unless `DEBUG` env var is set.

### Pydantic
- All MongoDB documents extend `pydantic.BaseModel` and live in `models.py`
- Runtime domain models (e.g. `Year`, `YearMarker`, `GuildConfig`) also extend `pydantic.BaseModel` and wrap the document models
- Use `model_config = ConfigDict(extra='ignore')` on document models to tolerate schema evolution
- Validate config sections with `ValidationError` and re-raise as a domain error where appropriate

### Async
- All I/O (Discord API, MongoDB) is async; use `asyncio.gather()` for parallel operations
- Bot extensions initialize synchronously inside `setup(bot)` by calling `loop.run_until_complete()`
- The web layer uses Quart (async Flask); route handlers are `async def`

### Discord (pycord)
- Slash commands use `@discord.slash_command()` or `SlashCommandGroup`
- Each command module is a pycord **extension** with a `setup(bot: Bot)` function
- Options use `@discord.commands.option()` decorators
- Permission checks: `from discord.ext import commands` then `@commands.check(predicate)`; `discord.commands` does NOT have `check` - it only exposes `option` and `SlashCommandGroup`; predicates live in `util.py` (`is_bot_owner`, `is_authorized_guild`, `has_announcements_role`)
- Error handling: `on_application_command_error` in `events.py` is the global handler - extension-level commands should raise naturally
- **Ephemeral responses**: use `ephemeral=True` only for errors and validation failures; successful command responses should be public (no `ephemeral` argument)

### MongoDB / Repository Pattern
- All database access goes through the repository classes in `repositories.py`
- Repositories are instantiated lazily via module-level `_get_repo()` helpers
- Use `upsert=True` (`$set`) for saves; never assume a document exists
- Index creation happens in `init_indexes()` on each repository; call this at extension load time
- Discord snowflake IDs are stored as `int` in MongoDB

### Web (Quart)
- All routes are registered in `routes.py` via `register_routes(app: Quart)`
- API routes return `jsonify(...)` with standard shapes: `{'error': '...'}` on failure, `{'success': True, 'message': '...'}` on success
- Discord IDs in JSON responses are serialized as **strings** to avoid JavaScript precision loss
- Validation uses Pydantic form models from `web/forms.py`; return `400` with `e.errors()` on `ValidationError`
- Mutations go through the audit logger (`web_app.audit_logger.log_change(...)`)

### JavaScript
- ES modules (`"type": "module"` in `package.json`)
- Linted with ESLint 10; run `npm run lint`
- Tested with Vitest; test files follow `*.test.js` naming
- No transpilation - targets the runtime directly

---

## Testing
Run all tests:
```
docker compose run --build --rm --quiet-build tests
```

### Python Tests
- Tests live in `tests/`; configured via `[tool.pytest.ini_options]` in `pyproject.toml`
- `asyncio_mode = "auto"` - async tests work without explicit `@pytest.mark.asyncio`
- All tests run with `TZ=UTC` (set in `conftest.py` before any imports)
- Uses **freezegun** to pin wall-clock time for deterministic calendar calculations
- Uses `unittest.mock` (`AsyncMock`, `MagicMock`, `patch`) - no additional mock library

#### Key fixtures (from `conftest.py`)
| Fixture | Purpose |
|---|---|
| `guild` / `make_guild` | Creates a `GuildConfig` and registers it in `config.guilds` |
| `mock_ctx` / `mock_ctx_factory` | Mock `ApplicationContext` with `.respond` tracked via `AsyncMock` |
| `mock_year_repo` | Patches `attubot.client.years._get_repo` - preferred for Year model tests |
| `mock_marker_repo` | Patches `attubot.client.markers._get_repo` - preferred for YearMarker tests |
| `mock_all_repos` | Patches both repos; returns `{'year': ..., 'marker': ...}` |
| `mock_db_and_repos` | Patches `db.get_db` and resets module-level repo singletons |
| `make_year` / `make_year_doc` | Factory fixtures for `Year` and `YearDocument` instances |

#### Conventions
- Use `mock_year_repo` / `mock_marker_repo` rather than directly patching internal state
- `xfail` marks document **known bugs** - when a fix lands the test becomes `XPASS`, which signals the marker should be removed
- Test constants: `TEST_GUILD = 1234567890`, `TEST_USER = 9876543210`, `TEST_CHANNEL = 5555555555`

#### Mock compensation rule
When a test mocks a framework mechanism, it inherits responsibility for testing what that mock hides. Two standing cases in this codebase:

- `bot.load_extension()` is mocked in `test_start_bot_loop.py` to test orchestration. Compensation: `TestExtensionImports.test_extension_imports_cleanly` in the same file does a real `importlib.import_module()` for each entry in `extensions_list` - decorators are evaluated at import time, so any bad attribute reference surfaces immediately. Whenever you add an extension file under `attubot/commands/`, verify this test still passes.
- Command tests call functions directly, bypassing `@commands.check` decorators. Compensation: permission predicates (`is_bot_owner`, `is_authorized_guild`, `has_announcements_role`) are tested in `test_util.py`. Whenever you add a new predicate or change an existing one, add or update its test there.

The general principle: if you write a test that mocks out a mechanism, ask "what behavior is this mock hiding?" and ensure that hidden behavior is covered at another level.

### JavaScript Tests
- Test files: `tests/*.test.js`
- Uses `jsdom` environment for DOM tests

### Linting
```bash
ruff check .           # Python lint
ruff format --check .  # Python format check
npm run lint           # JS lint
```
---

## Running Locally

### Recommended: Dev Container
Open in VS Code, accept "Reopen in Container" - Python 3.13 + MongoDB 8 are pre-configured.

### Manual
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
npm install
cp config/attu-bot.sample.toml assets/attu-bot.toml
# edit assets/attu-bot.toml with real values
python attu-bot.py bot   # or: python attu-bot.py web
```

### Docker
```bash
docker compose up --build -d
docker compose logs -f
```

---

## Important Patterns & Pitfalls

- **`TEST_MODE` env var**: when set, the bot exits cleanly after reaching ready state without a 60-second restart delay. Migrations are also skipped.
- **`DEBUG` env var**: enables `trace`/`debug`/`alert` log levels.
- **Config singleton**: `bot`, `config`, and `db` singletons are defined in `attubot/client/core.py` and re-exported from `attubot`. Extensions can import them from either path.
- **Guild authorization**: always check `guild_id in config.authorized_guilds` before acting. `config.guild(id)` raises `UnauthorizedGuild` for unknown guilds.
- **Snowflake precision**: Discord IDs exceed JavaScript's safe integer range - serialize them as strings in any JSON API response.
- **Rollover time storage**: stored as `rollover_minutes` (int, minutes since midnight) in MongoDB; the legacy string format (`"17:00"`) is handled by a `model_validator` in `GuildEpoch`.
- **`wip/` directory**: excluded from all linting and type checks; use it for exploratory/in-progress work.
- **`resvg` dependency**: the bot checks for `/usr/local/bin/resvg` at startup and exits if missing - it is bundled in the Docker image.
- **Error webhook**: unhandled exceptions in commands are forwarded to a Discord webhook via `logger.send_to_webhook(err)`.
- **Permission checks on slash commands**: use `@commands.check(predicate)` from `discord.ext.commands` - NOT `@discord.commands.check()`, which does not exist in pycord. All command modules use `from discord.ext import commands`.

---

## Reference Notes

Notes in `notes/` with relevant implementation details:

- [`button_usage.md`](notes/button_usage.md) - pycord `discord.ui.View` buttons (styles, rows, disabling, timeouts, persistent views)
- [`comment_style.md`](notes/comment_style.md) - comment formatting conventions (case, punctuation, section dividers, TODO tags)
- [`embed_usage.md`](notes/embed_usage.md) - discord embed construction and field usage
- [`starboard.md`](notes/starboard.md) - starboard feature spec and embed structure reference
- [`testing.md`](notes/testing.md) - test cases
- [`.meta.md`](notes/.meta.md) - guide for recreating this AGENTS.md and notes/ system in another repository
---

## File & Directory Layout

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
notes/                   # project notes (not code)
wip/                     # work-in-progress scratch space (excluded from lint)
```

# Personality

- use semicolons or regular dashes (-); never em-dashes
- do not include any extraneous punctuation
- write code comments in all lowercase including at the beginning of sentences, except where it would be unclear; prefer to be brief
- use american english spelling and grammar
- Use spaces for indentation always; avoid formats that require tabs
- prefer brief statements over long explanations
