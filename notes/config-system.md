# config system

## three tiers

1. **`.env`** - only `ATTU_CONFIG_FILE`
2. **`apps/bot/assets/attu-bot.toml`** - secrets and static config (tokens, DB URL, wiki credentials, WebAuthn, authorized guilds); copy from `config/attu-bot.sample.toml`
3. **MongoDB** - runtime guild-level settings (epoch, channels, roles, users, theme)

`NovaConfig` loads in three stages - code that touches the DB or bot must wait for the appropriate stage. use the provided `wait_for_*` async methods to gate on a stage.

## version constants

two independent version constants live in `apps/bot/nova_core/__init__.py`:

- **`__schema__`** - db migration version; bumped for every migration in `client/migrations.py`; compared against the version stored in MongoDB (`global_config.system.version`) to decide whether to run migrations
- **`__config_version__`** - minimum compatible TOML config file version; bumped only when the TOML file format changes (new sections, renamed keys, etc.); the TOML's `config_version` field is checked with `>=` against this value on startup

db-only migrations bump `__schema__` only. TOML format changes bump both and update `config/attu-bot.sample.toml`. migration execution is handled by `run_pending_migrations()` in `client/migrations.py`.

## adding a config field

pick the right tier first. static secrets and startup values belong in the TOML; operator-adjustable per-guild values belong in MongoDB.

### tier 2 - TOML (`apps/bot/assets/attu-bot.toml`)

- add the field to the relevant pydantic model in `nova_core/config.py`
- add it with a sensible placeholder value to `config/attu-bot.sample.toml`

### tier 3 - MongoDB (guild-level)

missing any of these steps causes the field to silently use its default in production.

- `packages/shared-models/attu_models/documents.py` - add to `GuildConfigDocument` with a default; `extra='ignore'` means keys not listed here are never read from MongoDB
- `apps/bot/nova_core/config.py` (`GuildConfig`) - add to the runtime model with the same default
- `apps/bot/nova_core/config.py` (`NovaConfig.load_guild()`) - pass the value explicitly when constructing `GuildConfig` from the document; missing this causes the field to silently use its default in production
- **roundtrip test** - save a document with the field set to a non-default value, reload via `load_guild()`, assert the value survives; this directly catches the hydration failure mode

### if the field gates an extension

- in the task that auto-activates it: call `bot.reload_extension()` + `bot.sync_commands()` on the `False → True` transition
- in `tasks/reload_watcher.py`: diff old vs. new value after `config.load_guild()` and reload or unload the extension so signal-triggered changes take effect without a restart
