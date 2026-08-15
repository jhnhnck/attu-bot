# pre-mortem - mongo-cutover

**bottom line:** proceed with revisions - no high risks; three medium risks need explicit handling in phase DoDs before work starts.

---

### risks

- [medium] integration - `migrate.py` must call `init_database(url, name)` before `run_pending_migrations()` because `run_pending_migrations()` calls `config.config_repo.get_system()` and `config.config_repo` is `None` until `init_database()` sets it; plan says "connect + run migrations" without specifying this ordering; phase 1 will discover it mid-implementation - probe: in phase 0 spike, write a one-liner that calls `run_pending_migrations()` against an empty table and confirm it works after `init_database()` but crashes before it

- [medium] scope - restoring `unique=True` on `MessageRepository`'s message_id index (phase 2) will fail at `create_index()` time if any duplicate message_ids exist in the live data; deduplication was enforced via upsert logic, not a db constraint, so edge cases from early operation are possible - probe: after phase 0 restore to mongo:8 dev, run `db.messages.aggregate([{$group:{_id:'$message_id',count:{$sum:1}}},{$match:{count:{$gt:1}}}])` and confirm zero results

- [medium] premise - phase 3 assumes `system.version == '2.5.5'` in prod; if the prod bot crashed mid-migration at any point in the past six months, the version could be at an intermediate state; the bot startup version assertion (phase 1) catches this at deploy time, but detecting it earlier avoids a deploy-time surprise - probe: before phase 3 begins, query prod `global_config.system.version` directly and document the result

- [medium] operational - prod `postgres_data` is an external named volume; the plan removes the postgres service but doesn't specify how long to keep the volume before deletion; if MongoDB shows data integrity issues in the first 24 hours, the volume is the only rollback path - probe: document explicit 24-hour hold on `postgres_data` deletion in phase 3 DoD

- [low] scope - `web_mode` and `ingestor_mode` flags on `NovaConfig` exist solely to skip migration calls; removing the migration calls from `on_load`/`on_ready` leaves these flags as dead code - addressed by adding explicit removal to phase 1 scope

- [low] dependency - `mongodb-database-tools` is hardcoded at `100.15.0` in the Dockerfile (line 51; a TODO comment acknowledges this); current version is compatible with Community Edition but will need bumping over time - noted; not blocking for this plan

- [low] scope - tests service in `docker-compose.dev.yml` uses `TEST_DB_URL` pointing at `ferret:27017`; removing FerretDB in phase 2 requires updating the tests service to point at the new `mongo` service; the plan mentions adding a `mongo:8` service but doesn't call this out explicitly in phase 2 DoD - addressed

---

### walking-skeleton check

**verdict: correct.** phase 0 is a genuine end-to-end probe - no code changes, touches every layer (data dump, wire protocol, mongorestore, bot startup against mongo:8). every later phase replaces a FerretDB assumption without introducing a new layer. phase 1 adds the `update` service but its wire is validated by phase 0's connectivity confirmation.

one addition: phase 0 DoD should require a document count comparison (FerretDB vs mongo:8 per collection) in addition to "bot starts." starting cleanly is necessary but not sufficient to confirm data fidelity.

---

### phase-order revisions

no reordering needed. current order is risk-first: data transfer (0) -> integration wiring (1) -> code cleanup (2) -> operational (3).

---

### definition-of-done additions

- phase 0 - add: per-collection document count matches between FerretDB and mongo:8 after restore; zero duplicate `message_id` rows in messages collection confirmed via aggregation; `init_database()` -> `run_pending_migrations()` sequencing confirmed working (spike)
- phase 1 - add: `migrate.py` explicitly documents calling `init_database(url, name)` then `run_pending_migrations()`; `web_mode` and `ingestor_mode` flags removed from `NovaConfig`
- phase 2 - add: tests service in dev compose updated to `TEST_DB_URL` pointing at `mongo` service; `docker compose run tests` passes with FerretDB services absent
- phase 3 - add: `system.version` queried from prod and confirmed `2.5.5` before cutover begins; old prod compose file backed up before replacement; `postgres_data` volume retained for minimum 24 hours post-cutover before deletion
