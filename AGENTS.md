# AGENTS.md - AttuBot / Doom Bot

Guidance for AI coding agents working in this repository.

---

## Project Overview

**AttuBot** (repo name: `doom-bot`) is a Discord bot for the Attu Project that automates in-universe timekeeping, year-transition announcements, wiki management, and related utilities. It is written in **Python 3.13** and ships as a Docker container.

There are two runnable modes, both launched from `attu-bot.py`:

- `bot` - the Discord bot (pycord)
- `web` - a Quart-based admin web interface

---

## Architecture

### Entry Point
- `attu-bot.py` - CLI dispatcher; selects `bot` or `web` mode via `sys.argv[1]`

### Package: `attubot/`
| File | Role |
|---|---|
| `__init__.py` | Module metadata, creates singleton `bot`, `config`, `db` instances; `/ping` command; `start_bot_loop()` |
| `events.py` | Bot event handlers (`on_ready`, `on_message`, `on_member_join`, `on_application_command_error`, `before_invoke`); `_shutdown()` helper |
| `config.py` | `NovaConfig` - three-stage config loader (`on_init` → `on_load` → `on_ready`); Pydantic models for all config sections |
| `models.py` | Pydantic models for MongoDB documents (`GuildConfigDocument`, `YearDocument`, etc.) |
| `repositories.py` | MongoDB repository classes (`ConfigRepository`, `YearMarkerRepository`, `YearRepository`) - all async |
| `db.py` | `MongoStorage` singleton; connects to MongoDB |
| `markers.py` | `YearMarker` runtime model + bot extension setup |
| `years.py` | `Year` runtime model + bot extension setup |
| `calendar.py` | Pure calendar math - `get_year_status()`, `get_year_span()`, `get_next_year()` |
| `tasks.py` | APScheduler background jobs |
| `jobs.py` | `JobWorker` - lightweight async task queue |
| `logging.py` | Custom `Logger` class (termcolor-based); use `get_logger(__name__)` everywhere |
| `migrations.py` | Schema migration table |
| `util.py` | Shared helpers |
| `wiki.py` | MediaWiki API integration |

### Package: `attubot/commands/`
Each file is a pycord extension (`setup(bot)` function) that registers a `SlashCommandGroup`.

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
- Error handling: `on_application_command_error` in `events.py` is the global handler - extension-level commands should raise naturally

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

### Python Tests
```bash
pytest                 # run all tests
```
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
| `mock_year_repo` | Patches `attubot.years._get_repo` - preferred for Year model tests |
| `mock_marker_repo` | Patches `attubot.markers._get_repo` - preferred for YearMarker tests |
| `mock_all_repos` | Patches both repos; returns `{'year': ..., 'marker': ...}` |
| `mock_db_and_repos` | Patches `db.get_db` and resets module-level repo singletons |
| `make_year` / `make_year_doc` | Factory fixtures for `Year` and `YearDocument` instances |

#### Conventions
- Use `mock_year_repo` / `mock_marker_repo` rather than directly patching internal state
- `xfail` marks document **known bugs** - when a fix lands the test becomes `XPASS`, which signals the marker should be removed
- Test constants: `TEST_GUILD = 1234567890`, `TEST_USER = 9876543210`, `TEST_CHANNEL = 5555555555`

### JavaScript Tests
```bash
npm test               # vitest run (single pass)
npm run test:watch     # vitest watch mode
```
- Test files: `tests/*.test.js`
- Uses `jsdom` environment for DOM tests

### Linting
```bash
ruff check .           # Python lint
ruff format --check .  # Python format check
npm run lint           # JS lint
```

## Combined Tests
```bash
docker compose run --build --rm --remove-orphans tests
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
- **Config singleton**: `config` in `attubot/__init__.py` is the global `NovaConfig` instance. Extensions import it directly from `attubot`.
- **Guild authorization**: always check `guild_id in config.authorized_guilds` before acting. `config.guild(id)` raises `UnauthorizedGuild` for unknown guilds.
- **Snowflake precision**: Discord IDs exceed JavaScript's safe integer range - serialize them as strings in any JSON API response.
- **Rollover time storage**: stored as `rollover_minutes` (int, minutes since midnight) in MongoDB; the legacy string format (`"17:00"`) is handled by a `model_validator` in `GuildEpoch`.
- **`wip/` directory**: excluded from all linting and type checks; use it for exploratory/in-progress work.
- **`resvg` dependency**: the bot checks for `/usr/local/bin/resvg` at startup and exits if missing - it is bundled in the Docker image.
- **Error webhook**: unhandled exceptions in commands are forwarded to a Discord webhook via `logger.send_to_webhook(err)`.

---

## File & Directory Layout

```
attu-bot.py              # entrypoint
attubot/                 # main package
  commands/              # slash command extensions (one group per file)
  web/                   # Quart web app
assets/                  # runtime assets (TOML config, templates, static)
config/                  # sample/reference config files (not used at runtime)
tests/                   # pytest + vitest test suites
scripts/                 # utility scripts (backup, migration, test runner)
notes/                   # project notes (not code)
wip/                     # work-in-progress scratch space (excluded from lint)
```

# Personality

- use semicolons or regular dashes (-); never em-dashes
- do not include any extranous punctuation
- write code comments in all lowercase including at the beginning of sentences, except where it would be unclear; prefer to be brief
- use american english spelling and grammar
- Use spaces for indentation always; avoid formats that require tabs
- prefer brief statements over long explanations
