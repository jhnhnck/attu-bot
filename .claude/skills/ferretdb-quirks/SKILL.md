---
name: ferretdb-quirks
description: footgun-catcher for AttuBot's FerretDB v2 + DocumentDB Postgres backend. trigger when editing files under `packages/shared-models/attu_models/`, `apps/bot/nova_core/client/migrations.py`, `scripts/ferret_init.sh`, or `scripts/create_dev_seed.sh`; when a file uses pymongo aggregation pipelines, indexes, sessions, or transactions; when answering questions about index creation, $lookup, multi-document transactions, change streams, mongodump, or "why does this mongo query not work in our db". the mongo-cutover plan retires this backend; until it lands, these limits are live.
---

# ferretdb quirks

scope: pinned to **FerretDB v2.7** (`ghcr.io/ferretdb/ferretdb:latest` resolves to 2.7.x at time of writing) backed by **DocumentDB v0.107.0-ferretdb-2.7.0** on Postgres 17. exact image tags live in `docker-compose.dev.yml`. if either tag changes, treat this skill as stale and re-verify the divergences below against [docs.ferretdb.io/migration/compatibility/](https://docs.ferretdb.io/migration/compatibility/) and the [FerretDB issue tracker](https://github.com/FerretDB/FerretDB/issues).

## the premise

FerretDB v2 is mostly invisible. it speaks the MongoDB 5.0+ wire protocol; pymongo connects unchanged; mongodump/mongorestore round-trip BSON without conversion (the dev seed in `assets/doombot-seed/` is a vanilla mongodump). the aggregation operators, query operators, write operators, and index shapes the repo currently uses are all supported.

llm training data has more real mongo than ferretdb in it; the risk is that a suggestion reaches for a feature that ferretdb v2 doesn't yet implement and produces a runtime error in prod that looks like mongo but isn't. the list below is the full set of divergences that matter for this codebase.

## the actual footguns

### 1. multi-document transactions are not implemented

| pymongo call | status |
|---|---|
| `client.start_session()` | supported (sessions exist) |
| `session.with_transaction(...)` / `start_transaction()` | **not implemented** |
| `commitTransaction` / `abortTransaction` wire commands | not implemented |

source: [compatibility/#session-commands](https://docs.ferretdb.io/migration/compatibility/) lists both `commitTransaction` and `abortTransaction` as `❌ Not implemented yet`.

the repo does not currently use transactions; do not introduce them. if a multi-step write needs atomicity, structure it so each step is independently safe under retry (the existing pattern is `update_one(..., upsert=True)` keyed by a stable id).

### 2. change streams are not implemented

`collection.watch()` will fail. tracking issue [#175](https://github.com/FerretDB/FerretDB/issues/175) is still open.

the repo's cross-process notification path is the hmac-signed bridge: the server posts to `/reload` on the bot's bridge (`apps/bot/nova_core/bridge/router.py`), which calls `config.load_guild()` / `load_theme()` synchronously in the bot process. the older db-polled reload-signal collection is gone. do not propose `watch()` as a "modernization."

### 3. `bulk_write` is not implemented

`collection.bulk_write([...])` (the wire-level `bulkWrite` command) returns `❌ Not implemented yet` per [compatibility](https://docs.ferretdb.io/migration/compatibility/).

`update_many`, `insert_many`, and `delete_many` are individual commands and **are** supported - those are what the repo uses (`migrations.py:358`, `migrations.py:451`, `migrations.py:475`). do not refactor a loop of `update_one` into a single `bulk_write` call; iterate or use `update_many` with a filter.

### 4. unique indexes on hot collections stall writes

postgres takes `ACCESS EXCLUSIVE` on the table for a non-concurrent `CREATE UNIQUE INDEX`, blocking all reads and writes for the duration of the index build. on collections with many millions of rows (`messages`, `signals` historically) this can lock the table for hours.

documentdb's `createIndexes` wrapper does not expose `CREATE INDEX CONCURRENTLY`; `unique=True` always takes the exclusive lock. the repo deliberately avoids `unique=True` on these collections and deduplicates via `update_one(filter, ..., upsert=True)` instead. see the in-code comments at `packages/shared-models/attu_models/repositories.py:329` (messages) and `packages/shared-models/attu_models/repositories.py:815` (reload_signals).

rule: never add `unique=True` to a collection that already has substantial production data without first checking row count and discussing the rollout. small or freshly-created collections are fine.

### 5. TTL indexes require a `Date` field, not a unix int

[docs.ferretdb.io/guides/ttl-indexes/](https://docs.ferretdb.io/guides/ttl-indexes/): "The field must have a `Date` type." our document models store timestamps as `int` (unix seconds) - see `WikiViewDocument.expires_at`, `EggDocument.hatches_at`, `ReminderDocument.created_at`. an `expireAfterSeconds` index on any of these will silently never delete anything.

the repo handles this manually: `WikiViewRepository.cleanup_expired()` runs `delete_many({'expires_at': {'$lte': time.time()}})` (`repositories.py:1256`). do not "improve" that into a TTL index without first changing the field type to BSON `Date` everywhere it is read or written.

### 6. unsupported/uncertain index types

| index type | status in v2.7 |
|---|---|
| single-field, compound, ascending/descending | ✅ supported |
| `unique` | ✅ supported (but see #4 above for the lock footgun) |
| `partialFilterExpression`, `sparse` | ✅ supported (issue [#2448](https://github.com/FerretDB/FerretDB/issues/2448) closed Jan 2025) |
| TTL (`expireAfterSeconds`) | ✅ supported - **but field must be Date type, see #5** |
| text (`{field: 'text'}`) | ✅ supported - **only one text index per collection** ([guides/full-text-search](https://docs.ferretdb.io/guides/full-text-search/)) |
| `hashed` | ⚠️ status unclear; not documented in v2 indexes guide. avoid. |
| `wildcard` (`{'$**': 1}`) | ❌ open issue [#2947](https://github.com/FerretDB/FerretDB/issues/2947) |
| 2dsphere / geospatial | ⚠️ partial - see open issues [#5529](https://github.com/FerretDB/FerretDB/issues/5529), [#5570](https://github.com/FerretDB/FerretDB/issues/5570). do not assume mongodb-equivalent results. |

the repo only uses single-field, compound, and `unique` (on small collections). nothing here needs hashed/wildcard/geo today.

## what is verified working for this repo's usage

these are confirmed by [docs.ferretdb.io/migration/compatibility/](https://docs.ferretdb.io/migration/compatibility/) (commands) and tracking issue [#1917](https://github.com/FerretDB/FerretDB/issues/1917) (closed June 2025, all aggregation stages and operators completed). do not rewrite working queries that use these.

- aggregation stages used in repo: `$match`, `$project`, `$sort`, `$limit`, `$group`, `$sample`, `$unwind`, `$count`
- aggregation expression operators used in repo: `$objectToArray`, `$size`, `$sum`, `$ne`
- update operators: `$set`, `$setOnInsert`
- query operators: `$exists`, `$ne`, `$lte`, `$gt`, `$regex`, `$in`
- write commands: `find`, `find_one`, `update_one`, `update_many`, `insert_many`, `delete_one`, `delete_many`, `find_one_and_update`, `aggregate`
- `upsert=True` on `update_one` / `update_many`

representative pipelines (do not rewrite): `repositories.py:720` ($sample), `repositories.py:731` ($objectToArray + $unwind + $group), `repositories.py:1097` (group + sort + limit leaderboard), `migrations.py:342` (distinct via $group).

## mongodump / mongorestore

works without flags. the dev seed pipeline is:

- `scripts/create_dev_seed.sh` - extracts a `tar.bz2` backup, strips heavy collections, leaves the BSON dump in `assets/doombot-seed/`
- `scripts/ferret_init.sh` - on container start runs `mongorestore --host ferret:27017 -u $POSTGRES_USER -p $POSTGRES_PASSWORD --nsExclude='doombot.<coll>' /tmp/seeds/doombot-seed`

`--nsExclude` is supported. there are no ferretdb-specific flags in either script and none are needed; if you find yourself reaching for `--oplog`, `--noIndexRestore`, or `--restoreDbUsersAndRoles`, stop - none of those address a real ferretdb gap, and we don't have the corresponding mongo features anyway (oplog is the change-stream shaped hole; users live in the postgres role table).

per the user's working notes, BSON mongodump from the prior real-mongo era restores into ferretdb v2 unchanged. no format conversion step exists or is needed.

## connection-string and pymongo client options

`packages/shared-models/attu_models/connection.py` sets only standard timeout knobs (`serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`, `maxIdleTimeMS`). all pass through the wire protocol unchanged.

- `retryWrites=true` (pymongo default): safe; ferretdb individual writes are idempotent at the session level even though sessions cannot wrap a transaction.
- `directConnection`: no replica set in this deployment; leave unset.
- `readPreference`, `readConcern`, `writeConcern`: ferretdb is single-node here and the `w`/`j` semantics map onto plain postgres commits; do not write code that branches on these.

## anti-patterns to never suggest

- `session.with_transaction(...)` or `client.start_session()` followed by `start_transaction()` - see #1.
- `collection.watch()` for cross-process notification - see #2; use `signals.py`.
- `collection.bulk_write([...])` - see #3; loop or use `update_many`.
- `unique=True` on `messages`, `starred_messages` (large), or any collection that has accumulated significant production data without confirming row count first - see #4.
- TTL `expireAfterSeconds` index on a field stored as `int` - see #5.
- wildcard indexes (`{'$**': 1}`) - not supported.
- geospatial queries with mongodb-equivalent precision assumptions - partial support; verify behavior.

## error-message tells

ferretdb [intentionally preserves mongodb error codes but not exact text](https://docs.ferretdb.io/migration/compatibility/): "FerretDB uses the same error names and codes as MongoDB, but the exact error messages may sometimes be different." pattern-match on `OperationFailure.code`, not on the string. example already in repo: `repositories.py:829` checks `e.code == 86` (IndexKeySpecsConflict) on index drop/recreate.

## when uncertain, the dev stack is cheap

`docker-compose.dev.yml` postgres data is on `tmpfs`. spin it up, run the suspect query against it, tear it down. cost is seconds, no shared state, nothing to clean up.

```bash
docker compose -f docker-compose.dev.yml up -d ferret-init
# then connect with mongosh or run a one-off pymongo script
```

prefer this to guessing.

## re-verification on version bump

before merging a `docker-compose.dev.yml` change that bumps either image tag:

1. re-read [docs.ferretdb.io/migration/compatibility/](https://docs.ferretdb.io/migration/compatibility/) - confirm transactions, change streams, bulkWrite still match section "the actual footguns" above.
2. skim the [FerretDB CHANGELOG](https://github.com/FerretDB/FerretDB/blob/main/CHANGELOG.md) and the [DocumentDB releases](https://github.com/FerretDB/documentdb/releases) for entries between the old and new tag.
3. update the version line at the top of this skill or delete it if findings change materially.
