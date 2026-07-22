# pre-mortem — nova-w5

**bottom line:** proceed with revisions — three changes folded into the plan before phase 0 starts (guilds stub, 501 fallback, `_AdminSession` boundary). no phase-order rework needed.

---

### risks

- [high] dependency — `ServerConfig` has no `guilds` field today; `GET /admin/guilds` needs a list of guild IDs to enumerate but the current config only parses `database`, `web`, `webauthn`, `bridge`. without it, the endpoint has nothing to hand the bridge. · probe: add `GuildEntry`/`AuthConfig` stubs to `config.py` in phase 0 with empty defaults; write a test that constructs `ServerConfig` with a populated `guilds` list and calls `GET /admin/guilds` with a mocked bridge — confirm it iterates the list.

- [high] dependency — `recalculate-starboard` fix operation requires `POST /bridge/fix/recalculate-starboard` which does not exist in `doom_bot/bridge/router.py`. phase 3's `fix.py` endpoint will call a bridge route that returns 404. without a mitigation, phase 3 ships with a broken endpoint. · probe: implement a `501 Not Implemented` fallback in `fix.py` when the bridge returns 404; add a test that mocks the bridge returning 404 and asserts the server returns 501; log the bridge-side TODO in `bugs.md`.

- [high] premise — dot-path config key traversal (`starboard.channel`, `ccboard.threshold`) is assumed to map directly to real `GuildConfigDocument` field names. if tests use plain dict mocks, field-name drift during nova-w3 feature migration won't be caught until integration. · probe: phase 2 tests must instantiate a real `GuildConfigDocument` with known values (not `{}` or `MagicMock()`); traverse via the dot-path function; assert the returned value matches. run before phase 2 merges.

- [medium] scope — `cmd.Cmd` session state entangled with dispatch methods makes phase 4 unit tests shallow; `cmdloop()` owns stdin so most state transitions can't be exercised without subprocess or monkey-patching. · probe: factor all mutable state and slug-resolution logic into a standalone `_AdminSession` dataclass with pure methods; `do_*` dispatch methods are thin wrappers; unit tests only ever construct and call `_AdminSession` directly.

- [medium] integration — slug generation is stateless (built per-request from live Discord data). if a guild or channel is renamed between `use <guild>` and a subsequent command, the cached slug resolves to a stale snowflake. not a correctness bug (user can `refresh`) but can surprise operators mid-session. · probe: document the session-cache contract in the `refresh` command's help text and in `plan.md`; no code change required.

- [low] operational — repl default server URL `http://localhost:8000` doesn't reach the server inside compose without `ATTU_SERVER_URL` override. · probe: add a startup hint if the server connection fails: `hint: inside compose, set ATTU_SERVER_URL=http://server:8000`.

---

### walking-skeleton check

**verdict: adequate.** phase 0's `GET /admin/ping` exercises the full stack: `AuthConfig` stub → `require_api_key` dep → admin router wiring in `main.py` → test via `TestClient`. it doesn't touch the bridge or db, which is correct — those are real in phases 1-3. the skeleton will surface import errors, router-prefix mismatches, and dep injection bugs before any endpoint logic is written.

one gap: the skeleton needs to confirm that `config.auth` and `config.guilds` are accessible on `app.state.config` inside the admin router, not just parseable at startup. the phase 0 test should assert `request.app.state.config.auth.api_keys` is reachable, not just that the endpoint returns 200.

---

### phase-order revisions

| original | proposed | reason |
|---|---|---|
| phase 1 scope: auth + listing | add `GuildEntry` and `AuthConfig` stubs to phase 0 scope | `GET /admin/guilds` in phase 1 can't enumerate guilds without `config.guilds`; unblocking this in phase 0 means phase 1 can be fully tested |
| phase 3: no fallback for missing bridge fix endpoint | add 501 fallback in fix.py when bridge returns 404 | prevents shipping a broken endpoint; the bridge-side TODO is logged separately |
| phase 4: session state in cmd.Cmd subclass | extract `_AdminSession` dataclass with pure methods | unlocks meaningful unit tests without subprocess/stdin mocking |

---

### definition-of-done additions

- phase 0 — add: test asserts `request.app.state.config.auth.api_keys` is reachable inside an admin route handler (not just that the config parses at startup)
- phase 1 — add: bridge mock asserts it is called exactly once per entry in `config.guilds` for `GET /admin/guilds`; 404 returned for an unrecognized slug on channel/role endpoints
- phase 2 — add: dot-path traversal test instantiates a real `GuildConfigDocument` (not a mock dict); field name mismatch produces 422, not an unhandled `AttributeError`
- phase 3 — add: `501` path for `recalculate-starboard` covered by a test mocking the bridge returning 404; bridge-side TODO logged in `bugs.md` at merge time
- phase 4 — add: manual smoke test record in `log.md` after first successful session against dev server
