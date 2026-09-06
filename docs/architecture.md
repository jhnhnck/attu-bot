# architecture

AttuBot (`doom-bot` repo) is a Discord bot for the Attu Project automating in-universe timekeeping, year-transition announcements, wiki management, and related utilities. Written in Python 3.13, shipped as a Docker container.

Entry point: `apps/bot/doom-bot.py` launches the Discord bot (pycord).

---

## package: `apps/bot/nova_core/`

| file | role |
|---|---|
| `__init__.py` | module metadata constants (`__version__`, `__schema__`, `__config_version__`, etc.) |
| `config.py` | `NovaConfig` - three-stage config loader (`on_init` → `on_load` → `on_ready`); pydantic models for all config sections including `GuildConfig` |
| `loader.py` | feature manifest loader; calls `mod.init_repos(db)` on each feature module after loading its manifest |
| `manifest.py` | `FeatureManifest` dataclass; describes a loadable bot feature |
| `webhook.py` | error webhook reporter; forwards unhandled exceptions to a Discord webhook |

## package: `apps/bot/nova_core/client/`

| file | role |
|---|---|
| `__init__.py` | startup pipeline - `start_bot_loop()`, `_check_deps()`, `_load_event_handlers()`, `_register_core_commands()`, `_load_extensions()`; `/ping` registered here as an intentional exception to the extension pattern |
| `core.py` | module-level singletons: `bot` (discord.Bot), `config` (NovaConfig), `db` (MongoStorage); leaf module - import always via `nova_core.client.core` |
| `events.py` | bot event handlers (`on_ready`, `on_message`, `on_member_join`, `on_application_command_error`, `before_invoke`); `_shutdown()` helper |
| `embeds.py` | `make_embed()` - standard embed builder with auto-theme color and timestamp |
| `markers.py` | `YearMarker` runtime model + bot extension setup |
| `years.py` | `Year` runtime model + bot extension setup |
| `calendar.py` | pure calendar math - `get_year_status()`, `get_year_span()`, `get_next_year()` |
| `messages.py` | message storage, `build_message_doc()`, edit/delete log embeds |
| `starboard.py` | starboard reaction processing (`handle_star_add`, `handle_star_remove`), embed builder, post sync logic |
| `families.py` | FamilyEcho client - `is_family_file`, `get_viewer_url` (httpx POST), family repo accessors |
| `logo.py` | logo generation and SVG-to-PNG rendering via `resvg` |
| `migrations.py` | schema migration table |
| `util.py` | shared helpers - `theme_color()`, `format_message_link()`, `break_at_newline()`, permission check predicates |

## package: `apps/bot/nova_core/commands/`

each file is a pycord extension (`setup(bot)` function) registering a `SlashCommandGroup`.

| file | slash group | purpose |
|---|---|---|
| `debug.py` | `/version`, `/pong`, `/color` | top-level diagnostic commands; deeper diagnostics moved to the admin api (`/admin/ops/info/*`) |
| `fix.py` | (none) | background job functions for repair and maintenance (channel/guild backfill, ccboard regen/purge/recover/cleanup/recount); no slash commands, invoked via bridge ops endpoints |
| `marker.py` | `/marker` | save, set, and clear year marker messages |
| `query.py` | `/query` | channel pin queries |
| `stars.py` | `/stars` | starboard browsing (`random`, `lost`, `recheck`) and `/stars leaderboard` (`most-stars`, `most-starred`, `most-given`, `top-messages`) |
| `time.py` | `/time` | in-universe time controls - advance, pause, resume, dilate |
| `wiki.py` | `/wiki` | wiki lookup (`random`, `lookup`) and admin (`block`); uses `WikiLinkView` / `WikiLookupView` |
| `year.py` | `/year` | year check, search, and link commands |
| `link.py` | `/link` | FamilyEcho family tree commands (`family list`, `family view`, `family set`, `family upload`) |
| `trees.py` | `/trees` | family tree editor link, show, share, and unshare commands |
| `eggs.py` | `/egg`, `/eggs` | egg collection game - collect, hatch, view, give, progress, `/eggs leaderboard` (`hatched`, `collected`) |
| `remind.py` | `/remind` | in-universe date reminders - add, list, cancel |
| `cc_stars.py` | `/cc stars` | ccboard browsing and leaderboards (walking-skeleton stub; `/stars leaderboard top-messages` covers ccboard today) |

## package: `apps/bot/nova_core/database/`

| file | role |
|---|---|
| `__init__.py` | `init_database()` - connects storage and seeds module-level repo singletons; bot is the index-creation leader |
| `connection.py` | re-exports `MongoStorage`, `AsyncMongoClient`, error classes from `attu_models` |
| `models.py` | re-exports all document classes from `attu_models.documents` |
| `repositories.py` | re-exports all repository classes from `attu_models.repositories` |

## package: `packages/shared-models/attu_models/`

shared mongo documents, repositories, and `MongoStorage`, used by both the bot and the server. feature-owned repositories live with their feature package instead (`nova_core/starboard/`, `ccboard/`, `eggs/`, `wiki/`, `trees/`, `reminders/`).

| file | role |
|---|---|
| `connection.py` | `MongoStorage` singleton; `connect()`, `get_db()`, `close()` |
| `documents.py` | pydantic document models - `GuildConfigDocument`, `ThemeDocument`, `SystemConfigDocument`, `YearMarkerDocument`, `YearDocument`, `MessageDocument` and its `MessageAuthor` / `MessageContent` / `MessageRefs` parts |
| `repositories.py` | async repository classes - `ConfigRepository`, `YearMarkerRepository`, `YearRepository`, `MessageRepository` |

## package: `apps/bot/nova_core/tasks/`

background tasks managed by `TaskScheduler`. each task extends `BaseTask` (`on_start`, `next_run`, `run`).

| file | role |
|---|---|
| `base.py` | `BaseTask` ABC - defines the task lifecycle interface |
| `scheduler.py` | `TaskScheduler` - registers tasks, drives `_run_loop()` per task, exposes `running_tasks()` |
| `nova_year.py` | `NovaYearTask` - checks for year rollover on schedule; `job_construct_year_links()` helper |
| `message_backfill.py` | `MessageBackfillTask` - periodic scan of configured channels to store unseen messages |
| `logo_update.py` | `LogoUpdateTask` - refreshes the bot's avatar on a schedule |
| `db_backup.py` | `DatabaseBackupTask` - weekly mongodump to the configured backup path |
| `error_hook.py` | `ErrorHookTask` - periodic flush of queued webhook error notifications |
| `reload_watcher.py` | `ReloadWatcherTask` - polls MongoDB for reload signals |
| `presence.py` | `PresenceUpdateTask` - updates bot presence to reflect hatched egg count; 30-minute schedule |
| `egg_cleanup.py` | `EggCleanupTask` - deletes non-egg messages from egg threads |
| `reminder.py` | `ReminderTask` - dynamic scheduling; delivers in-universe date reminders when haracalnde dates arrive |

## package: `apps/bot/nova_core/eggs/`

| file | role |
|---|---|
| `data.py` | rarity constants, hatch durations, drop weights, hatch pools |
| `emojis.py` | SVG→PNG rendering and Discord custom emoji upload (`ensure_egg_emojis`) |
| `hatching.py` | core game logic - `hatch_date()`, `collect_egg()`, `hatch_egg()`, `run_hatch_animation()`, `ensure_eggs_ready()` |

## package: `apps/bot/nova_core/ccboard/`

| file | role |
|---|---|
| `__init__.py` | package init |
| `auditor.py` | periodic board audits and sweep logic |
| `builder.py` | embed pipeline - builds ccboard post embeds from messages |
| `documents.py` | ccboard-specific pydantic document models |
| `manager.py` | core reaction processing and post management |
| `migration.py` | ccboard-specific schema migrations |
| `repositories.py` | ccboard repository classes |
| `watcher.py` | reaction event watcher |

## package: `apps/bot/nova_core/modlog/`

| file | role |
|---|---|
| `__init__.py` | package init |
| `handlers.py` | moderation log event handlers - member join/leave/ban, channel/role/emoji changes, nickname and timeout updates |

## package: `apps/bot/nova_core/features/`

| file/dir | role |
|---|---|
| `__init__.py` | built-in feature packages index |
| `_test_feature/` | reference implementation for feature manifests; used in tests |

## package: `apps/bot/nova_core/bridge/`

small http server (uvicorn, port 5050) running inside the bot process. the server calls it to trigger live bot actions. secured with HMAC-SHA256 per request.

| file | role |
|---|---|
| `__init__.py` | exports the bridge fastapi app |
| `hmac.py` | signing and verification - `sign(secret, method, path, body, timestamp)` returns `t=<ts>,v1=<hex_digest>`; `verify()` fastapi dependency |
| `router.py` | fastapi routers (signed + unsigned paths); `launch_bridge(config)` starts uvicorn as an asyncio task |
| `discord_integration.py` | guild/channel/role lookups via pycord; used by bridge route handlers |

signing payload: `ts\nMETHOD\npath\nbody`. header: `x-bridge-signature: t=<ts>,v1=<hex_digest>`. client is `apps/server/attu_server/bridge_client.py`; CLI for manual calls is `scripts/bridge_curl.py`.

## package: `packages/attu-wiki/attu_wiki/`

| file | role |
|---|---|
| `__init__.py` | `get_wiki()` singleton accessor; `setup(bot)` extension entry point |
| `client.py` | `WikiClient` - top-level client composing auth, pages, search, and admin APIs |
| `auth.py` | `AuthApi` - login and CSRF token handling |
| `pages.py` | `PagesApi` - `get()`, `edit()`, `get_summary()`, `get_random_summary()` |
| `search.py` | `SearchApi` - full-text and title search, `site_info()` |
| `admin.py` | `AdminApi` - user block with retry logic |
| `models.py` | pydantic models - `SearchResult`, `PageSummary`, `SiteInfo`, `PageThumbnail` |

## package: `packages/attu-logging/attu_logging/`

| file | role |
|---|---|
| `__init__.py` | `get_logger(__name__)` factory; exports `Logger` |
| `config.py` | logging setup, level configuration, `DEBUG` env var handling |
| `webhook.py` | `send_to_webhook()` - forwards warn/error/fatal/alert to Discord webhook |

use `from attu_logging import get_logger` everywhere; never the stdlib `logging` module directly.

## package: `apps/server/attu_server/`

| file | role |
|---|---|
| `main.py` | fastapi app factory + lifespan + gzip middleware |
| `config.py` | `ServerConfig`, `BridgeConfig`, `DatabaseConfig`, `WebConfig` - loaded from `attu-bot.toml` |
| `bridge_client.py` | async httpx client for calling the bridge using the identical HMAC signing scheme |
| `deps.py` | fastapi dependency providers (db, config, bridge, api-key auth) |
| `preflight.py` | startup checks (bridge reachable, db connected) |
| `api/admin/` | api-key protected `/admin` routes - `guilds.py` (list, channels, roles), `config_routes.py` (get/patch guild config keys), `features.py` (enable/disable), `reload.py` (guild/theme/system), `ops.py` (backfill, ccboard repairs, triggers, info, inspect), `slugs.py` (guild slug resolution); driven by `scripts/nova_admin.py` |

---

## file and directory layout

uv workspace; member packages live under `apps/` and `packages/`.

```
apps/
  bot/                       # discord bot
    doom-bot.py              # entrypoint
    nova_core/               # main package
      bridge/                # hmac-authenticated http server (uvicorn, port 5050) for bot->server ipc
      ccboard/               # ccboard reaction-board logic, embed pipeline, audits
      client/                # discord-specific runtime (singletons, events, features)
      commands/              # slash command extensions (one group per file)
      database/              # init_database() + shims re-exporting attu_models
      eggs/                  # egg game core logic
      features/              # built-in feature manifests
      modlog/                # moderation log event handlers
      tasks/                 # background task scheduler and task implementations
    assets/                  # toml config, hatch.toml, static/emoji, doombot-seed
    Dockerfile
    pyproject.toml
  server/                    # fastapi server + future svelte spa entry point
    attu_server/             # server package (config, bridge client, api routes)
    Dockerfile
    pyproject.toml
packages/
  shared-models/
    attu_models/             # canonical mongo documents, repositories, MongoStorage
    pyproject.toml
  attu-logging/
    attu_logging/            # get_logger() factory, webhook reporter
    pyproject.toml
  attu-wiki/
    attu_wiki/               # mediawiki api client (WikiClient)
    pyproject.toml
config/                      # sample/reference config files (not used at runtime)
scripts/                     # utility scripts (backup, migration, test runner, bridge_curl)
tests/                       # pytest test suites
docs/                        # mkdocs source: architecture, config system, features, style, to-do, bugs
.claude/plans/               # active multi-phase plans; archived/ holds shipped ones
wip/                         # work-in-progress scratch space (excluded from lint)
```
