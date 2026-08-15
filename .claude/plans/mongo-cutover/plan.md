# mongo-cutover

## goals

1. production bot running against MongoDB Community Edition (`mongo:8`); FerretDB and Postgres services removed from both compose files
2. update container established: `doom-bot.py migrate` mode + compose `update` service precedes `core`/`bot` on every startup
3. migration history reset to an empty table; `system.version = '2.5.5'` is the hard baseline enforced at bot startup; `ready_migration_table` retired
4. FerretDB-specific workarounds removed from codebase; ferretdb-quirks skill archived

## non-goals

- reactions schema migration (`dict[str, list[int]]` -> array of objects) - deferred
- MongoDB multi-document transactions in migration functions
- GuildConfigDocument sub-dict typing (separate cleanup)
- any nova-core workstream work

## constraints

- nova-w3 must be closed before this plan starts
- prod is at commit `aa9115b9` / schema `2.5.5`; old migration history is dropped, not ported
- single engineer; no push or deploy without explicit instruction
- `docker compose run tests` must pass at every phase merge

## accepted risks

one risk accepted going in: the prod FerretDB data export (mongodump) has never been tested end-to-end against a mongo:8 restore in this environment; phase 0 retires this before any code is written. second: `migrate.py` must call `init_database(url, name)` before `run_pending_migrations()` because `run_pending_migrations()` reads `config.config_repo` which is only set by `init_database()`; this pulls in the full repo wiring and, transitively, the pycord import chain from `nova_core.client.core`; pycord is installed in the image and safe to import, but the update container will create unused singleton objects - acceptable. phase 0 includes a spike to confirm this sequencing works before phase 1 implements it.

---

### phase 0 - data round-trip (walking skeleton)

**scope:** no code changes. prove the data transfer works before touching the codebase.

- spin up a standalone `mongo:8` container locally (or temporarily add to dev compose) with credentials matching what phase 2 will use (`MONGO_INITDB_ROOT_USERNAME` / `MONGO_INITDB_ROOT_PASSWORD`)
- seed dev FerretDB via the normal `ferret-init` flow to get a representative dataset
- run `mongodump` against dev FerretDB; `mongorestore` to local mongo:8
- temporarily set `MONGO_URL` in dev TOML to the mongo:8 connection string; start bot
- verify: bot reaches `on_ready`, all collections readable, no errors in logs
- spike: write a standalone script that calls `init_database(url, name)` then `run_pending_migrations()` against the local mongo:8; confirm it runs without error and exits cleanly

**dod:**
- bot starts cleanly against mongo:8 restored data with no errors
- all feature commands reachable in `/debug` output
- per-collection document count matches between FerretDB and mongo:8 (compare before and after restore)
- zero duplicate `message_id` rows in messages collection confirmed: `db.messages.aggregate([{$group:{_id:'$message_id',count:{$sum:1}}},{$match:{count:{$gt:1}}}])` returns empty
- `init_database()` -> `run_pending_migrations()` sequencing spike passes; approach documented

**merge gate:** no code to merge; gate is documented evidence (log snippet + doc count table) that bot started clean against mongo:8

---

### phase 1 - migration reset + update container

**scope:** rip out old migrations; establish the update container pattern. dev switches to mongo:8 this phase.

- `nova_core/client/migrations.py`: delete all migration functions and `ready_migration_table`; leave `load_migration_table = []` (empty); keep `run_pending_migrations()`, `@migration` decorator, and `MigrationError` for future use
- `nova_core/__init__.py`: `__schema__` stays `'2.5.5'`
- `nova_core/config.py`: remove both `run_pending_migrations()` calls (lines ~522 and ~597); remove the `web_mode`/`ingestor_mode` migration skip logic and the flags themselves (vestigial once migration calls are gone); add startup assertion after DB connect: if `system.version != nova_core.__schema__`, log critical and refuse to start
- new `nova_core/client/migrate.py` (~30-40 lines): parse TOML via `tomllib` to extract DB URL + name, call `init_database(url, name)` (sets `config.config_repo`), then `run_pending_migrations(stage='load')`, exit 0 on success / non-zero on failure; pycord is imported transitively but is safe (see accepted risks)
- `doom-bot.py`: add `migrate` as a valid mode alongside `bot`
- `docker-compose.dev.yml`: add `mongo` service (`mongo:8` with auth env vars); add `update` service (same bot image, command `python doom-bot.py migrate`, `depends_on: mongo`); add `depends_on: update: condition: service_completed_successfully` to `bot`; update bot `MONGO_URL` to point at `mongo:27017`
- `docker-compose.prod.yml`: same additions targeting `core` service
- tests: update mocks to remove migration expectations from `on_load`/`on_ready`; add test for version mismatch refusal

**dod:**
- `docker compose run update` exits 0 against local mongo:8
- `docker compose run bot` starts and reaches ready state without running any migration code
- a forced version mismatch (manually set `system.version` to `'0.0.0'`) causes bot to log critical and exit 1
- `web_mode` and `ingestor_mode` flags absent from `NovaConfig`
- `ruff check .` clean; `docker compose run tests` passes

**merge gate:** phase 0 gate passed; no `doom_bot` import references (nova-w3 closed)

---

### phase 2 - FerretDB workaround removal + code cleanup

**scope:** code-only cleanup; no schema changes. MongoDB Community Edition assumed on dev.

- `attu_models/repositories.py` `MessageRepository.init_indexes()`: restore `unique=True` on message_id index; remove FerretDB workaround comment
- `attu_models/repositories.py` `ReloadSignalRepository.init_indexes()`: remove the `OperationFailure` / code 86 recovery branch
- `nova_core/wiki/repositories.py`: replace `delete_expired()` with TTL index (`expireAfterSeconds=0` on `expires_at`) in `init_indexes()`; delete `delete_expired()` method and its caller in the cleanup task or wherever it is called
- `nova_core/eggs/repositories.py`: rewrite `get_user_egg_stats()` as a single aggregation pipeline; remove the `async for` streaming loop
- `StarredMessageDocument`: drop `weighted_total` field; remove `_sync_totals()` pipeline update for it; wherever `weighted_total` appears in logs, compute inline (`total_normal + total_super * 1.5`) at log time
- both compose files: remove `ferret`, `postgres`, `ferret-init` services; tests service `TEST_DB_URL` updated to point at `mongo:27017`; prod compose also gets a `mongo:8` service with auth env vars (credentials via `.env` or secret file)
- prod compose: remove `postgres_data` volume declaration; add `mongo_data` named volume for persistence
- archive `ferretdb-quirks` skill (move to `.claude/skills/archived/`)
- `notes/to-do.md` line 78: update entry to reflect completion

**dod:**
- no FerretDB workaround comments remain in codebase (`grep -r "FerretDB\|ferretdb" apps/ packages/` returns nothing)
- `wiki_views` TTL index creates correctly; no `delete_expired` calls remain
- `get_user_egg_stats` is a single aggregation round-trip; confirmed via test
- `weighted_total` field absent from `StarredMessageDocument`; no references in repositories or tests
- `docker compose run tests` passes with FerretDB services absent (tests hit local `mongo:8`)
- `ruff check .` clean

**merge gate:** phase 1 merged to trunk

---

### phase 3 - prod cutover

**scope:** operational only; no code changes. runs after phases 1+2 are on trunk and nova-core cutover gate passes.

- `mongodump` from prod FerretDB (exec into prod ferret container or use the weekly backup at the backup path)
- set up mongo credentials in prod `.env` (or docker secret) matching the auth env vars added to prod compose in phase 2
- `mongorestore` to prod `mongo:8` (started via the new compose service)
- update prod TOML `MONGO_URL` to `mongodb://user:pass@mongo:27017/doombot?authSource=admin`
- standard deploy: `git pull && docker compose up --build -d` in prod worktree at `/srv/services/doom-bot`
- `update` service runs first, asserts `system.version == '2.5.5'`, exits 0
- `core` service starts
- smoke test: `/ping` responds, check `/debug version`, inspect logs for errors

**dod:**
- `system.version` confirmed `'2.5.5'` in prod FerretDB before cutover begins (query prod DB directly)
- old prod compose file backed up before replacement
- prod bot online against MongoDB Community; no errors in first 10 minutes of logs
- `docker ps` shows no ferret or postgres containers running
- `postgres_data` volume retained for minimum 24 hours post-cutover, then deleted; `mongo_data` volume present and non-empty
- backup task (`db_backup.py`) verified it runs against MongoDB Community (next scheduled tick or triggered via `/fix`)

**merge gate:** phases 1+2 merged to trunk; nova-core cutover gate passed

---

## status

| phase | status |
|---|---|
| 0 - data round-trip | not started |
| 1 - migration reset + update container | not started |
| 2 - FerretDB workaround removal | not started |
| 3 - prod cutover | not started |
