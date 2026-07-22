# Pre-mortem — nova-w4 casino bot scaffold

**Bottom line:** proceed with revisions — three specific changes to the plan before phase 1 starts; no full rework required.

---

### Risks

- [high] **premise** — `secrets.SystemRandom()` does not exist in the Python stdlib. `secrets` exposes free functions (`secrets.choice()`, `secrets.randbelow()`, `secrets.randbits()`) — not a `SystemRandom` class. `random.SystemRandom()` is cryptographically secure (uses `os.urandom`) but requires `import random`, which the plan bans. any implementer who types `secrets.SystemRandom().choice(...)` gets `AttributeError: module 'secrets' has no attribute 'SystemRandom'` at runtime, not a lint error. · probe: add `python -c "import secrets; secrets.SystemRandom()"` as a one-liner to the phase 0 DoD, expect `AttributeError`, and update the constraint + all phase pitfalls to name the correct pattern: `secrets.choice()`, `secrets.randbelow()`.

- [high] **integration** — phase 0 imports `nova_core` but only names nova-w2 as a dependency. `nova_core` does not exist yet; it is the doom_bot → nova_core rename from nova-w1. if nova-w1 is not merged, `import nova_core` fails at startup and phase 0 cannot reach ready state. · probe: `python -c "import nova_core"` inside the dev container as the first phase 0 step; if it fails, add nova-w1 to the prerequisites and import `doom_bot` instead until the rename lands.

- [high] **dependency** — ferretdb multi-document transaction support is unverified. the entire banking atomicity design (phases 2–4) depends on `start_session()` / `start_transaction()` / `abort_transaction()` working. ferretdb has documented compatibility gaps (unique-index locking, `$in` on `_id`); transaction support may be partial or absent. · probe: `tests/python/component/test_mongo_session.py` in phase 1 — write, abort, read-back-empty against the actual dev ferretdb instance. this probe is already in the plan; the DoD must include an explicit pivot criterion: if the test fails against ferretdb, stop and run `plan-revise` before phase 2.

- [medium] **integration** — phase 3 coin_flip opens a mongodb session via `MongoStorage.get_client()`, but there is no specified mechanism for a feature to receive the `MongoStorage` instance. the nova-w2 `FeatureContext` loader is assumed to expose storage, but the contract (`nova-core.md`) does not define `FeatureContext`'s fields. if nova-w2 delivers a context that lacks a storage handle, the session-per-command pattern requires a global or a redesign. · probe: before phase 3 starts, read the nova-w2 merge diff and confirm `FeatureContext` (or equivalent) includes a storage handle; if not, file a nova-w2 issue and agree on the interface before starting coin_flip.

- [medium] **scope** — no player account initialization path. `BankAccountRepository.debit()` raises `InsufficientFundsError` when the balance document is missing — this is also the first-time-player case. a new user has no account and no balance. the plan has no `/register` command, no initial-balance grant, and no auto-create-on-first-use logic. every new player's first command will fail with `InsufficientFundsError`. · probe: decide the initialization rule before phase 2 code review (options: auto-create with 0 balance on first debit attempt, or require a `/casino register` command that mints an initial grant); add the chosen path to phase 2 scope.

- [medium] **scope** — the `S311` ruff un-ignore is deferred to phase 3. casino code is written in phases 0, 1, and 2 without the guard active. an accidental `import random` in `start_casino_loop()`, a document, or a repository would not be caught until phase 3 at the earliest. the lint gate should apply from the first line of casino code. · probe: move the `S311` per-directory override to phase 0 scope; add `ruff check apps/casino/ --select S311` to the phase 0 DoD.

- [low] **scope** — the lottery draw task schedule is described as "configurable" but no TOML key, format, or default is specified. the feature can't be deployed or tested without a concrete config field. · probe: specify the key before phase 4 (`[features.lottery] draw_interval_hours = 24` or similar); add it to the phase 4 scope and the example `casino.toml`.

- [low] **expertise** — pymongo async session/transaction API is new territory for this codebase. the correct context-manager pattern for async pymongo (`async with await client.start_session() as s: async with s.start_transaction(): ...`) differs subtly from sync pymongo and from `asyncio`-style context managers. · probe: the phase 1 component test is the right surface; add a comment in the test noting the double-`async with` pattern so the next reader doesn't simplify it incorrectly.

---

### Walking-skeleton check

**verdict: acceptable with one addition.** phase 0 touches every infrastructure layer (workspace, config, mongo, bot client, compose). it does not stub the session layer or banking — those are additive, not new-layer insertions, so they don't need phase-0 stubs. the one missing piece: the `S311` ruff override is tooling that applies from the first casino file written; move it into phase 0 alongside the workspace wiring (see revisions table below).

---

### Phase-order revisions

| original | proposed | reason |
|---|---|---|
| phase 3 — add S311 ruff override | phase 0 — add S311 ruff override | safety gate must apply from the first line of casino code, not when games are added; phases 0–2 write casino code without the guard if deferred |

no other reordering. the ferretdb probe is correctly placed at phase 1 (before banking); banking before games is correct; lottery last is correct.

---

### Definition-of-done additions

- **phase 0** — add: `python -c "import nova_core"` succeeds inside the dev container (verifies nova-w1 prerequisite); if not, stop and add nova-w1 to the prerequisites before continuing. add: `ruff check apps/casino/ --select S311` exits 0 with no violations (S311 override active from phase 0). add: pivot criterion — if `import nova_core` fails and nova-w1 is not yet merged, import `doom_bot` as a temporary stand-in and note the import as a TODO for when nova-w1 lands.

- **phase 1** — add explicit pivot criterion: if `tests/python/component/test_mongo_session.py` fails against dev ferretdb (write + abort + read-back does not work), do not proceed to phase 2. run `plan-revise` to redesign banking around compare-and-swap with compensating writes before continuing. add: double-`async with` pattern comment in the component test to guard against future simplification.

- **phase 2** — add: account initialization path defined and implemented (`auto-create with 0 balance` or `/casino register` — chosen before phase 2 code review). add: `InsufficientFundsError` must distinguish "account not found" from "balance too low" in the error message (separate conditions in `debit()`).

- **phase 3** — remove: S311 ruff override (moved to phase 0). add: the correct CSPRNG call pattern (`secrets.choice()` / `secrets.randbelow()`) is used — not `secrets.SystemRandom()` (which does not exist) and not `random.SystemRandom()` (which requires `import random`). DoD grep: `git grep 'SystemRandom' apps/casino/` returns 0 lines.

- **phase 4** — add: lottery schedule TOML key documented in `casino.toml` example and in phase 4 scope. add: `secrets.SystemRandom()` → `secrets.choice()` correction applied throughout.
