# nova-core modularization contract

architectural decisions and workstreams for the nova_core refactor: a fully modular, multi-bot platform built from the current doom-bot codebase.

<!-- toc -->
- [context](#context)
- [naming decisions](#naming-decisions)
- [feature taxonomy](#feature-taxonomy)
- [feature manifest design](#feature-manifest-design)
- [config restructure](#config-restructure)
- [admin repl client](#admin-repl-client)
- [second bot: casino](#second-bot-casino)
- [workstreams](#workstreams)
- [cutover gate](#cutover-gate)
- [see also](#see-also)
<!-- /toc -->

## context

doom-bot was built for one specific deployment (attu project) and has outgrown its original structure. features are woven into three core files rather than being self-contained:

- event handlers in `client/events.py` directly import and call per-feature code
- tasks manually listed in `tasks/__init__.py` `register_bot_tasks()`
- guild config fields hard-typed into `GuildConfig` and `GuildConfigDocument`

the driving goal is to build a second bot (a banking/casino/lottery bot) that shares the same core infrastructure but runs a completely different feature set. features must be independently loadable, removable, and portable without editing core files.

## naming decisions

| old name | new name | reason |
|---|---|---|
| `doom_bot` (package) | `nova_core` | neutral; no bot identity baked in |
| `attu_models` (package) | connection/storage infra only | features own their own documents; package name tbd |

the rename is a hard prerequisite. no other workstream starts until import paths are clean.

## feature taxonomy

| layer | what belongs here | examples |
|---|---|---|
| core | always loaded; everything depends on it | bot client, config, logging, bridge, database connection |
| base package | always loaded; housekeeping bundle no bot can omit | ping, version, db-backup, error-hook, reload-watcher, bridge health |
| platform services | core-adjacent; other features may depend on them | message storage (`client/messages.py`) |
| features | manifest-driven; independently loadable and removable | starboard, ccboard, eggs, wiki, reminders, trees, modlog, logo-update |
| attu-specific features | features that will not travel to other bots | timekeeping (nova_year), markers, year links |
| casino-specific features | new features in the second bot | banking, casino games, lottery |

**note on starboard/ccboard coexistence:** both are features with manifests. the guild-level `ccboard.enabled` flag handles runtime switching during the transition. the toml features list controls whether either loads at all. when starboard is retired, remove it from the attu toml features list and delete the package.

**note on platform services:** message storage is a platform service, not a feature, because starboard and ccboard both import from it. it lives in core. if a future bot needs neither, it may be omitted - but the dependency must be declared.

## feature manifest design

each feature package's `__init__.py` exports a `FeatureManifest` instance:

```python
from nova_core.manifest import FeatureManifest

manifest = FeatureManifest(
    name='ccboard',
    tasks=[manager_task, auditor_task],
    event_handlers={
        'on_raw_reaction_add': handle_reaction_add,
        'on_raw_reaction_remove': handle_reaction_remove,
        'on_raw_reaction_clear': handle_reaction_clear,
        'on_raw_reaction_clear_emoji': handle_reaction_clear_emoji,
    },
    setup=setup,                      # existing pycord setup(bot) fn for slash commands
    guild_config_key='ccboard',
    guild_config_model=GuildCCBoard,
    document_classes=[ReactionDocument, BoardEntryDocument],
    repository_classes=[ReactionRepository, EntryRepository],
    migrations=[...],                 # feature-owned migration list
)
```

the core loader reads `[features]` from the toml, finds each manifest, and wires:
- calls `bot.load_extension()` for slash commands via `setup`
- registers each event handler via `bot.listen()`
- registers tasks with the scheduler
- registers document/repo classes for index init
- appends feature migrations to the migration runner in declaration order

**per-bot feature selection:** `[features]` list in the toml. missing features have no manifest loaded; no core edits required to add or remove a feature.

```toml
[features]
enabled = ["ccboard", "eggs", "wiki", "reminders", "trees", "modlog"]
```

## config restructure

### toml changes

```toml
[bot]
name = "AttuBot"
welcome_message = "welcome to the archipelago {mention}"
# branding strings previously hardcoded in client/events.py

[auth]
api_keys = ["key1", "key2"]   # for the admin repl client; manually managed

[[guilds]]
id = 123456789012345678
role = "primary"

[[guilds]]
id = 987654321098765432
role = "secondary"

[[guilds]]
id = 111222333444555666
role = "test"

[features]
enabled = ["ccboard", "eggs", "wiki", "reminders", "trees", "modlog"]

[features.eggs]
# per-feature toml config if needed
```

### runtime GuildConfig

feature-specific guild config moves from hard-typed fields to a keyed bag:

```python
class GuildConfig(BaseModel):
    id: int
    channels: GuildChannels
    epoch: GuildEpoch
    roles: GuildRoles
    users: GuildUsers
    features: dict[str, BaseModel] = {}   # keyed by feature name; value validated by feature's model
```

`GuildConfigDocument` in the shared package already stores feature config as `dict` blobs (`starboard: dict = {}`, `ccboard: dict = {}`); the document layer requires no change.

### guild roles

| role | meaning |
|---|---|
| `primary` | main production guild |
| `secondary` | secondary production guild |
| `test` | mirrors some primary features for testing; debug/fix endpoints available |

the `primary`/`secondary` named config keys are removed. code that referenced `config.primary_guild` by name is updated to iterate `[g for g in config.guilds if g.role == 'primary']`.

## admin repl client

a python repl (`scripts/nova_admin.py`) that talks to the fastapi server. auth via `Authorization: Bearer <api_key>` header; keys are in the toml `[auth]` section.

### name resolution

no snowflakes as arguments. the fastapi server exposes:

```
GET /admin/guilds                       # list: {id, name, slug}
GET /admin/guilds/{slug}/channels       # list: {id, name, slug}
GET /admin/guilds/{slug}/roles          # list: {id, name, slug}
```

slug generation lives on the server: strip non-alphanumeric, lowercase, spaces to dashes. collisions get `-2`, `-3` suffix. the repl caches on `use <guild>`, refreshes with `refresh`.

### session model

```
nova-admin> guilds                          # list all guilds: slug | real name
nova-admin> use attu                        # select guild; fetches+caches channels/roles
nova-admin> channels                        # list channels: slug | real name | type
nova-admin> roles                           # list roles: slug | real name
nova-admin> config get starboard.channel    # fetch value
nova-admin> config set starboard.channel announcements
nova-admin> feature enable ccboard
nova-admin> feature disable starboard
nova-admin> reload guild
nova-admin> reload theme
nova-admin> fix recalculate-starboard
nova-admin> refresh                         # bust the channel/role cache
nova-admin> exit
```

implementation: `cmd.Cmd` from stdlib; no extra dependencies. `httpx` for http calls (already a project dependency).

### fastapi admin endpoints

the server grows an `/admin/` router, gated on `Authorization: Bearer` against `config.auth.api_keys`. endpoints cover: guild info, config get/set, feature enable/disable, reload triggers, fix/debug operations. the server calls the bridge internally for bot operations; the repl never touches the bridge directly.

## second bot: casino

lives in `apps/casino/` with its own entry point and toml. shares `nova_core` infrastructure; loads no doom-bot features.

**casino-specific engineering constraints:**

- banking requires atomic debit/credit; use mongodb multi-document sessions in the banking repository. current repository pattern does not use sessions; add session support to `BaseRepository` before building the banking feature
- casino games require cryptographically secure randomness; use `secrets.SystemRandom()`, not `random`. document this in the banking/casino feature's pitfalls section

casino features are built manifest-native from day one; no legacy coupling to clean up.

## workstreams

### workstream 1 - structural prerequisites

*nothing else starts until this is done*

- rename `doom_bot` package to `nova_core`; update all import sites, docker config, entrypoint scripts
- rename/restructure `attu_models`: shared package becomes connection and storage infrastructure only; document and repo classes move to feature ownership
- strip attu-specific strings from `client/events.py` and elsewhere into `[bot]` toml section
- flatten guild config from `primary`/`secondary` named keys to `[[guilds]]` array with `role` field
- remove `doom_bot`-named strings from all user-facing responses in core

### workstream 2 - feature manifest system

- define `FeatureManifest` dataclass and `FeatureContext` loader
- core loader reads `[features].enabled` from toml; discovers and loads manifests; wires tasks, event handlers, slash commands, document/repo registrations, and migrations
- base package defined explicitly: ping, version, db-backup, error-hook, reload-watcher, bridge health; always loaded before the manifest pass
- per-bot feature selection: toml `[features].enabled` list; missing features are silent no-ops

### workstream 3 - feature migration

*prove the pattern with one complete feature; template for all others*

- eggs first: self-contained, own package already, minimal cross-feature dependencies
- ccboard next: newer, better structured, will travel to both bots
- remaining features in dependency order: modlog, wiki, reminders, trees, starboard (last; deprecated)
- each migration: manifest declared, documents owned by feature, tasks through manifest, events through manifest, migrations attached to feature, existing tests passing

### workstream 4 - casino bot scaffold

- `apps/casino/` entry point with its own toml
- add mongodb session support to base repository pattern
- banking feature: `BankAccountDocument`, `TransactionDocument`, `TransactionRepository`; atomic debit/credit via sessions
- casino and lottery features built manifest-native
- no doom-bot features loaded; shares only `nova_core` infrastructure

### workstream 5 - fastapi admin endpoints + repl client

- fastapi server grows `/admin/` router; `Authorization: Bearer` gate against `config.auth.api_keys`
- server exposes: guild/channel/role listing with slugs, config get/set, feature enable/disable, reload triggers, fix/debug operations
- server calls bridge internally for bot operations; admin layer is clean http only
- `scripts/nova_admin.py`: `cmd.Cmd` repl, `httpx` calls, guild/channel/role name resolution, no snowflakes as arguments

## cutover gate

*runs after all workstreams are green; prod branch stays frozen until this gate passes*

- [ ] no `doom_bot` or `attu_models` import references remaining anywhere in the repo
- [ ] toml config loader emits a clear error on old-format keys (not a silent default)
- [ ] mongodb compatibility verified against current prod schema; no data loss on deploy
- [ ] admin repl connects to staging, resolves guild/channel names, executes a config round-trip
- [ ] all existing tests pass against `nova_core` package name
- [ ] docker images build and healthcheck passes with new package name
- [ ] deploy trunk to prod; run pending migrations; smoke test core features

## see also

- [agents.md](agents.md) - architecture, coding conventions, rules
- [dev/dev_setup.md](dev/dev_setup.md) - local dev workflow and deploy steps
- [features/ccboard.md](features/ccboard.md) - ccboard feature spec (first feature to migrate under the new pattern)
- [features/tasks.md](features/tasks.md) - task scheduler overview and BaseTask lifecycle

---

## metadata

```yaml
last_updated: 22 July 2026
```
