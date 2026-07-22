---
name: bug-hunt
description: structured debugging playbook for doom-bot — python async bot, bridge/router, discord.py, mongodb/motor, docker compose test harness. trigger on "find this bug", "track down the issue", "debug X", "why is X broken", "hunt down a bug", "something's wrong with", "help me debug", "unexplained crash", "why does this crash"; when behavior is incorrect and the cause is unknown; when a third-party library throws a cryptic error. not for writing features, code review, or performance profiling.
---

## reproduce first

pin the exact inputs, state, and sequence that trigger the bug. a bug you cannot reproduce reliably cannot be fixed reliably.

## narrow scope

ask: is the bad value coming from the caller, the function, or the boundary between them?

- **lint/type first** — ruff catches many bugs before they become runtime failures:
  ```bash
  ruff check .
  ```
- **run the failing test in isolation before reading code** — confirms the failure is real and shows the exact error:
  ```bash
  docker compose run tests pytest path/to/test.py::TestClass::test_name -x -s --tb=long
  ```

## specific module (location roughly known)

1. read the tests — they encode expected behavior; run just that module's suite first.
2. trace the bad value — follow the single wrong value from its origin through every transformation; don't read the whole file.
3. binary-search the call stack — insert a check at the midpoint; wrong before or after? repeat until invariants first break.
4. add assertions — `assert` around your hypothesis; let the runtime tell you when the assumption breaks.
5. `git bisect` — mark a good and bad commit, let git binary-search; finds the culprit in ~7 steps even across hundreds of commits.

## unknown location

1. grep for the symptom — search the error string, the wrong output value, or the bad property name; usually lands you in the right file immediately. if the crash originates inside a third-party or vendored dependency, search that library's issue tracker and changelog for the exact error string before bisecting.
2. work backwards from the observable failure — find where the bad output is rendered or returned, then trace backwards through callers; don't guess forward.
3. diff against known-good — `git diff <last-good-tag>` to surface recent changes; bugs introduced recently are almost always in the diff.
4. eliminate variables — comment out features, simplify inputs, revert configs until the bug disappears; what you just removed is the cause.

## zoom out — is this a symptom?

once you've found the exact line that breaks, pause before fixing it. ask:

- **does this same wrong assumption appear elsewhere?** grep for the pattern, not just the instance. if three other callsites make the same mistake, the fix belongs one level up.
- **why was this assumption wrong in the first place?** if the answer is "the caller shouldn't have to know this", the boundary between modules is leaking — fix the invariant at the boundary, not the guard at every callsite.
- **has this class of bug appeared before?** `git log --all -S "<symptom string>"` or `git log --grep="<keyword>"` to find prior related fixes.
- **is the data model forcing this code to be defensive?** if the bug required adding a null check or fallback default, ask whether the type or schema should have prevented it. see the `pydantic` skill for model patterns.

if any of these flag a broader issue, note it separately — fix the immediate bug, then surface the structural problem as a follow-up.

## doom-bot specific tools

### test suite

```bash
docker compose run --rm tests                                          # full suite
docker compose run --rm tests pytest tests/python/unit/test_foo.py    # single file
docker compose run --rm tests pytest path/to/test.py::Class::test -x -s --tb=long  # single test, verbose
docker compose run --rm tests pytest tests/python/unit/ -k "keyword"  # filter by name
```

### async-specific patterns

missing `await` is the most common silent bug in async python — it never raises, it just returns a coroutine object and nothing runs:

```python
# wrong: returns coroutine, doesn't execute
result = some_coroutine()

# if you suspect this, check:
import inspect
print(inspect.iscoroutine(result))  # True means you forgot await
```

`asyncio.current_task().get_name()` identifies which task you're in when behavior differs by execution context.

### bridge / router

- `router.py` is the first place to look for bridge runtime errors — most issues surface there as unhandled exceptions or wrong response codes
- check the hmac/auth layer first if requests are being rejected unexpectedly (`BridgeConfig.secret` + `X-Hub-Signature-256` header)
- `_bridge_started` guard: if the bridge appears to not start or double-starts, check the lockout flag and the task reference
- the health endpoint (`GET /health`) is the fastest end-to-end smoke test for the bridge without needing a real discord event

### discord.py / bot init

- `bot.is_ready()` is true after the READY event but before `_do_ready_init()` completes — it does not signal that the bot's own init (database, bridge startup, etc.) is done. use `bot._bot_initialized` for that guard.
- `@bot.listen` decorators run at import time — if an event handler isn't firing, check the import path, not the handler body.
- if a slash command isn't registering, check `_load_extensions()` and whether the cog loaded without error before `bot.run()`.

### structlog

- structlog is configured at startup via `attu_logging.configure()`. if log output is wrong or missing, check call order: configure must run before any `get_logger()` call creates a bound logger.
- correct pattern: `import structlog; logger = structlog.stdlib.get_logger(__name__)`
- `logging.getLogger()` bypasses structlog's processors — don't use it in bot code.

### mongodb / motor

- motor is async: a missing `await` on a motor call returns a coroutine object, not a document. the error usually surfaces several frames later as a type error on the result.
- most query bugs are projection issues — print the raw document before any filtering or field access to confirm what the DB actually returned.
- for motor in tests: check that the mock returns the right shape, not just a truthy value. see the `mock-compensation` skill for mock patterns.

## meta-principle

most bugs are wrong assumptions, not wrong code. find which assumption broke; don't read all the code hoping to spot the error.
