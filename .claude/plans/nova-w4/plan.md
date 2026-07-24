# nova-w4 — casino bot scaffold

## context

the nova-core modularization project builds a second discord bot (`apps/casino/`) that shares `nova_core` infrastructure but loads a completely different feature set. there is no existing casino entry point, no banking feature, and no casino games. this workstream builds them from scratch — manifest-native from day one.

**dependencies:** nova-w1 (doom_bot → nova_core rename) must be complete before phase 0 can import `nova_core`; nova-w2 (feature manifest system) must be complete before phases 2+. the walking skeleton (phase 0) stubs feature loading so it can run in parallel with w2; all later phases require the real `FeatureManifest` loader.

runs parallel with nova-w3 (feature migration).

---

## goals

each goal is a co-equal, grep-checkable end state. the workstream ships when all hold.

1. **casino bot entry point is a workspace member and reaches ready state.**
   check: `python apps/casino/casino-bot.py bot` against dev mongo logs ready state with no features loaded; `grep 'apps/casino' pyproject.toml` returns the member entry.

2. **`MongoStorage` exposes the async client for session creation; no existing call sites broken.**
   check: `MongoStorage.get_client()` exists and returns the `AsyncMongoClient`; `grep -rn 'get_client' apps/bot/ apps/server/` returns 0 lines; `python scripts/run_tests.py` green.

3. **banking feature is atomic.**
   check: `BankAccountRepository` and `TransactionRepository` exist under `apps/casino/casino_bot/features/banking/`; `debit()` and `credit()` accept an optional `session` kwarg; `tests/python/component/test_banking_atomic.py` covers the rollback case (debit succeeds, transaction insert raises → balance unchanged).

4. **casino game pattern is established with cryptographic randomness.**
   check: at least one casino game manifest exists and is loadable by the nova_core feature loader; `git grep 'import random' apps/casino/` returns 0 lines.

5. **lottery feature is manifest-native.**
   check: lottery manifest exists with a draw task registered via the manifest (not hardcoded); `git grep 'import random' apps/casino/` returns 0 lines.

---

## non-goals

- no doom-bot or attu features loaded by the casino bot
- no admin repl (nova-w5 scope)
- no production deployment (cutover gate scope)
- no UI beyond discord slash commands

---

## constraints

- **nova-w1 dependency**: `import nova_core` requires the doom_bot → nova_core rename from nova-w1. if nova-w1 is not yet merged, substitute `import doom_bot` as a stand-in and mark the import as a TODO.
- **nova-w2 dependency**: phase 0 stubs feature loading; phases 2+ wire real `FeatureManifest` instances. do not start phases 2+ until nova-w2 is merged to trunk.
- **atomic banking**: mongodb multi-document sessions required for debit/credit. no single-document tricks as shortcuts. verify ferretdb transaction support before phase 2 begins (phase 1 component test is the gate).
- **cryptographic randomness**: use `secrets.choice()`, `secrets.randbelow()`, and `secrets.randbits()` from the `secrets` stdlib module directly. `secrets.SystemRandom` does not exist — calling it raises `AttributeError`. `random.SystemRandom()` is cryptographically secure but requires `import random`, which is banned. `import random` is a build break in `apps/casino/`; a ruff `S311` per-directory override (active from phase 0) enforces this.
- **manifest-native**: every casino feature declares a `FeatureManifest` from day one. no legacy coupling to clean up later.
- **integer balances**: `balance_tokens` and all monetary amounts are `int` (token units). no floats, no `Decimal`.

---

### phase 0 — walking skeleton

thinnest possible casino bot that exercises every layer: workspace wiring, config loading, mongo connection, nova_core bootstrap, feature loader with empty list, ready state.

**scope:**
- root `pyproject.toml`: add `apps/casino` to `[tool.uv.workspace].members` and `casino-bot` to workspace sources
- `apps/casino/pyproject.toml`: workspace member `casino-bot`; deps: `attu-logging`, `nova_core` (post-w1 rename; import `doom_bot` as stand-in if nova-w1 not yet merged), `attu-models`, `py-cord[speed]<3`, `pymongo>=4.6.0`, `pydantic`, `tomlkit`
- `apps/casino/casino-bot.py`: entry point; `attu_logging.configure()` as line 1; `mode` arg (`bot` only); calls `start_casino_loop()`; same crash-and-restart wrapper as `apps/bot/doom-bot.py`
- `apps/casino/casino_bot/__init__.py`: `start_casino_loop()` — reads `casino.toml`, calls `MongoStorage.connect()`, instantiates nova_core bot client, calls feature loader with `features=[]` (empty list for now), runs the discord event loop; logs "casino ready" in `on_ready`
- `apps/casino/casino.toml` (dev config example): `[bot]`, `[mongo]`, `[features] enabled = []`
- `apps/casino/Dockerfile`: modeled on `apps/bot/Dockerfile`; add `casino` service to `docker-compose.dev.yml`
- root `pyproject.toml [tool.ruff.lint.per-file-ignores]`: add `"apps/casino/**" = []` entry that omits `"S311"` from the un-ignored set (re-enables S311 for all casino code from phase 0 onward)

**dod:**
- `python -c "import nova_core"` succeeds in the dev container; if it fails, nova-w1 is a prerequisite — switch to `import doom_bot` as a stand-in and note it as a TODO
- `python apps/casino/casino-bot.py bot` against dev mongo logs ready state and does not crash
- `uv sync` resolves cleanly with `apps/casino` as a workspace member
- `docker compose -f docker-compose.dev.yml config` validates without error
- `ruff check apps/casino/ --select S311` exits 0 with no violations (S311 active for casino dir)
- `grep 'import doom_bot' apps/casino/` returns 0 lines if nova-w1 is complete (or exactly the stand-in TODO lines if not)
- `python scripts/run_tests.py` returns green (existing suite unaffected)
- **pivot criterion:** if `import nova_core` fails and nova-w1 has no merge timeline, add nova-w1 as a hard prerequisite and do not start phase 0 until it lands

**merge gate:** green CI; `apps/casino` workspace member entry in root `pyproject.toml`; S311 override active

---

### phase 1 — mongodb session support

adds session capability to the shared storage layer so banking can perform atomic multi-document operations. modifies shared infrastructure; must not break existing call sites.

**scope:**
- `packages/shared-models/attu_models/connection.py`: add `get_client() -> AsyncMongoClient` method; raises `RuntimeError('MongoStorage not initialized; call connect() first')` if called before `connect()`; the method simply returns `self.client`
- no existing repository methods modified; no signature changes to `ConfigRepository`, `MessageRepository`, etc.
- `tests/python/component/test_mongo_session.py` (component marker): verify `get_client()` exists; open a session via `await storage.get_client().start_session()`; perform a write and abort; assert the write is not visible post-abort (proves session semantics work against the dev mongo backend)

**pitfalls:**
- ferretdb transaction support is unverified. **before merging phase 1, confirm via the component test that `start_session()` + `start_transaction()` + `abort_transaction()` works against the actual dev mongo/ferretdb instance.** if ferretdb does not support multi-document transactions, surface immediately and do not proceed to phase 2 until the contract is revised (a queue-based atomic pattern may be the fallback).

**pitfalls (continued):**
- the correct async pymongo transaction pattern is a double `async with`: `async with await client.start_session() as s: async with s.start_transaction(): ...`. this differs from sync pymongo and from standard asyncio context managers. add an inline comment in the component test so future readers don't simplify it incorrectly.

**dod:**
- `MongoStorage.get_client()` exists; raises on pre-connect call
- `grep -rn 'get_client' apps/bot/ apps/server/` returns 0 lines
- `tests/python/component/test_mongo_session.py` passes against dev ferretdb under the `component` marker (write + abort + read-back-empty against the actual dev instance)
- `python scripts/run_tests.py` returns green
- **pivot criterion:** if `test_mongo_session.py` fails against dev ferretdb (transactions not supported), do not proceed to phase 2 — run `plan-revise` to redesign banking around a compare-and-swap + compensating-write pattern before continuing

**merge gate:** green CI; component session test passing against ferretdb; pivot criterion documented and acknowledged

---

### phase 2 — banking feature

the casino bot's core financial layer. atomic debit/credit is the invariant that drove session support in phase 1. **requires nova-w2 complete.**

**scope:**
- `apps/casino/casino_bot/features/banking/documents.py`: `BankAccountDocument` (user_id: int, guild_id: int, balance_tokens: int, created_at: int, updated_at: int); `TransactionDocument` (txn_id: str, user_id: int, guild_id: int, amount: int, txn_type: str, reference_id: str | None, created_at: int)
- `apps/casino/casino_bot/features/banking/repositories.py`: `BankAccountRepository` (init_indexes, get, upsert, debit, credit, get_or_create); `TransactionRepository` (init_indexes, insert, list_for_user); `debit(user_id, guild_id, amount, *, session=None)` uses a conditional `find_one_and_update` with `{balance_tokens: {$gte: amount}}` filter to enforce overdraft protection atomically; raises `InsufficientFundsError(reason='insufficient_balance')` if balance < amount; raises `InsufficientFundsError(reason='account_not_found')` if no account document exists; `get_or_create(user_id, guild_id)` creates an account with `balance_tokens=0` if none exists (called by `/casino register` or auto-invoked on first command)
- `apps/casino/casino_bot/features/banking/__init__.py`: `FeatureManifest` (name='banking', document_classes=[BankAccountDocument, TransactionDocument], repository_classes=[BankAccountRepository, TransactionRepository], setup=setup); slash command `/casino register` auto-creates the player account (calls `get_or_create`); also auto-creates account on first `/flip` or `/lottery buy` if the player skips registration
- `tests/python/component/test_banking_atomic.py` (component marker): start a session, debit an account, raise before inserting the transaction doc, abort, assert balance unchanged
- `tests/python/unit/test_banking_documents.py`: pydantic model validation; `InsufficientFundsError(reason='insufficient_balance')` raised when balance < amount; `InsufficientFundsError(reason='account_not_found')` raised when no account doc; `get_or_create` creates a 0-balance account on first call and returns the existing one on second call

**pitfalls:**
- **prerequisite — reconnect bug (bugs.md):** `_db.connect()` in `on_ready` closes and recreates the mongo client on every Discord reconnect. before phase 2 registers any feature that holds a DB reference, move the initial `connect()` call to before the event loop starts. features must call `_db.get_db()` lazily on each operation, never cache the returned object at setup time.
- `balance_tokens` is `int` only — no floats, no `Decimal`. any payout multiplier must be applied as integer arithmetic (e.g., 2× payout = `amount * 2`, not `amount * 2.0`).
- overdraft check must be inside the session transaction, not a pre-flight read-then-write. the conditional `find_one_and_update` with `{$gte: amount}` filter is the correct pattern; a separate `get()` followed by `debit()` is a race condition.
- the `InsufficientFundsError` must distinguish "account not found" from "balance too low": the `find_one_and_update` with `{$gte: amount}` returns no match for both cases. do a follow-up `get()` to distinguish them and set `reason` accordingly.
- banking has no randomness — `secrets.choice()` etc. are for games (phase 3+). document this in a docstring on `BankAccountRepository` so reviewers don't add a PRNG.

**dod:**
- `BankAccountRepository.debit()` raises `InsufficientFundsError` with correct `reason` field for both "insufficient_balance" and "account_not_found" cases (unit test)
- `get_or_create()` creates a 0-balance account for new users (unit test)
- `/casino register` command wired via manifest
- `tests/python/component/test_banking_atomic.py` passes under the `component` marker (abort rollback confirmed)
- banking manifest is loadable by the nova_core feature loader (nova-w2 must be merged)
- `git grep 'import random' apps/casino/` returns 0 lines
- `python scripts/run_tests.py` returns green

**merge gate:** green CI; atomicity test passing; no float balance fields; `InsufficientFundsError` reason-field unit tests present; `get_or_create` test present

---

### phase 3 — first casino game (coin flip)

establishes the casino game pattern: manifest-native, cryptographic randomness, integrates with banking for bet/payout. coin flip is the reference implementation — subsequent games follow the same shape.

**scope:**
- `apps/casino/casino_bot/features/coin_flip/`: `__init__.py` (FeatureManifest, name='coin_flip'), `commands.py` (slash command `/flip <side: heads|tails> <bet: int>`); flow: validate bet > 0 → auto-create account if needed → debit via banking session → resolve via `secrets.choice(['heads', 'tails'])` → credit 2× bet on win or insert loss transaction → reply with result embed
- **before starting this phase:** confirm that nova-w2's `FeatureContext` (or equivalent) exposes the `MongoStorage` instance so the command handler can call `storage.get_client()` to open a session; if not, file a nova-w2 issue and agree on the interface before writing the command
- the debit + resolve + credit/loss sequence runs inside a single mongodb session (opened from `storage.get_client().start_session()`); no partial state possible
- `tests/python/unit/test_coin_flip.py`: mock banking repos; assert debit called before result resolves; assert credit called on win, not on loss; control outcome by patching `secrets.choice`
- update `apps/casino/casino.toml` example: add `coin_flip` to `[features] enabled`

**pitfalls:**
- `secrets.choice(['heads', 'tails'])` is the correct call — not `secrets.SystemRandom().choice(...)` (that attribute does not exist) and not `random.choice(...)` (banned). `git grep 'SystemRandom' apps/casino/'` should return 0 lines.
- the pre-condition check for nova-w2 `FeatureContext` storage access (noted above) must be done before writing the command, not discovered at integration time.

**dod:**
- nova-w2 `FeatureContext` confirmed to expose a storage handle (or the interface is agreed before code starts)
- `/flip` command registered by the coin_flip manifest and wired by the nova_core feature loader
- `git grep 'import random' apps/casino/` returns 0 lines
- `git grep 'SystemRandom' apps/casino/` returns 0 lines
- `tests/python/unit/test_coin_flip.py` passes
- `python scripts/run_tests.py` returns green

**merge gate:** green CI; no `import random`; no `SystemRandom`; FeatureContext storage access confirmed

---

### phase 4 — lottery feature

lottery differs from instant games: players buy tickets in advance, a draw runs on a schedule, one winner is selected from the pool. manifest-native; uses banking for ticket purchases and winner payout.

**scope:**
- `apps/casino/casino_bot/features/lottery/documents.py`: `LotteryTicketDocument` (ticket_id: str, user_id: int, guild_id: int, draw_id: str, purchased_at: int); `LotteryDrawDocument` (draw_id: str, guild_id: int, status: Literal['open','closed','drawn'], ticket_ids: list[str], winner_ticket_id: str | None, prize_tokens: int, draw_at: int, drawn_at: int | None)
- `apps/casino/casino_bot/features/lottery/repositories.py`: `TicketRepository`, `DrawRepository`
- `apps/casino/casino_bot/features/lottery/__init__.py`: FeatureManifest (name='lottery', tasks=[draw_task], document_classes=[...], repository_classes=[...])
- slash commands: `/lottery buy <ticket_count: int>` (debits tokens per ticket); `/lottery status` (shows current draw, pool size, time until draw); `/lottery history` (last N draws and winner)
- `draw_task`: runs on configurable schedule (read from `[features.lottery] draw_interval_hours = 24` in `casino.toml`; default 24); closes the current draw (`status='closed'`); fetches all tickets for the draw; picks winner via `secrets.choice(ticket_ids)`; credits winner; updates draw document to `status='drawn'`; announces in configured channel; opens a new draw
- `tests/python/unit/test_lottery.py`: mock repos; assert winner selection uses `secrets.choice` (patch it to control outcome); assert credit called for winner; assert draw document updated to `status='drawn'`; assert empty-pool case skips selection and reopens

**pitfalls:**
- draw closure must happen atomically with winner selection: set `status='closed'` in one update, then fetch all tickets for the closed draw, then pick. do not accept new ticket purchases after `status='closed'`. the `/lottery buy` command must check `status == 'open'` and reject if closed.
- an empty ticket pool (no buyers) must be handled — draw_task skips selection and reopens with a log message; do not call `secrets.choice([])` (raises `IndexError`).
- `secrets.choice(ticket_ids)` — not `secrets.SystemRandom().choice(...)` (that attribute does not exist).

**dod:**
- `/lottery buy`, `/lottery status`, `/lottery history` commands registered via manifest
- `draw_task` registered via manifest (not hardcoded in startup)
- `[features.lottery] draw_interval_hours` key present in example `casino.toml`
- `git grep 'import random' apps/casino/` returns 0 lines
- `git grep 'SystemRandom' apps/casino/` returns 0 lines
- `tests/python/unit/test_lottery.py` passes (including empty-pool case)
- `python scripts/run_tests.py` returns green

**merge gate:** green CI; draw task registered via manifest; empty-pool guard present; no `import random`; no `SystemRandom`; schedule config in example toml

---

## risks

the pre-mortem (`pre-mortem.md`) is the canonical risk record. one risk merits calling out inline: **ferretdb multi-document transaction support.** the entire banking atomicity design depends on `start_session()` / `start_transaction()` / `commit_transaction()` working correctly against the dev and prod ferretdb instance. the phase 1 component test (`test_mongo_session.py`) is the gate — if it fails against ferretdb, do not proceed to phase 2. the fallback (a single-document compare-and-swap with a compensating `undo_debit` on failure) would require a contract revision before continuing.

---

## minimum viable adoption?

yes. phase 0 alone ships a runnable second bot and proves the workspace can host multiple apps. each subsequent phase is independently mergeable. the workstream does not need to complete in full before the casino bot is useful — banking alone (phases 0-2) is a deployable feature set.

---

## status

| phase | status |
|---|---|
| 0 — walking skeleton | pending merge |
| 1 — mongodb session support | not started |
| 2 — banking feature | not started |
| 3 — first casino game (coin flip) | not started |
| 4 — lottery feature | not started |
