# nova-w4 — bug log

<!-- bug-triage appends here -->

## open

### on_ready reconnect will invalidate in-flight DB references in future phases

**File**: `apps/casino/casino_bot/__init__.py:41`

**Problem**: `_db.connect()` called inside `on_ready` fires on every Discord reconnect. `MongoStorage.connect()` closes and recreates the client each time. For phase 0 (no DB callers) this is safe. In phases 2+, features that hold a reference via `_db.get_db()` at setup time will see the old (closed) database object after a reconnect.

**Impact**: Low now; medium for phases 2–4. Fix: move the initial connect out of `on_ready` and only call it once at startup; handle reconnect separately, or verify that features always call `_db.get_db()` lazily on each operation rather than caching the returned object.

---

### Casino Dockerfile omits git-info stamp stage

**File**: `apps/casino/Dockerfile`

**Problem**: The bot Dockerfile has a `git-info` stage that stamps `__version__` and `__build_time__` into `nova_core/__init__.py` via sed. The casino Dockerfile skips this, so `from nova_core import __build_time__` will always log the static placeholder string.

**Impact**: Low — cosmetic for a walking skeleton; fix when the casino bot moves toward production.

---

### Pre-existing unit test failure: test_sets_discord_http_logger_to_debug

**File**: `tests/python/unit/test_start_bot_loop.py::TestSetupDiscordLogging::test_sets_discord_http_logger_to_debug`

**Problem**: `AssertionError: assert 30 == 10` — test expects discord HTTP logger at DEBUG (10) but it's WARNING (30). Present on baseline before any nova-w4 changes. Unrelated to casino scaffold.

**Impact**: Low — the test is checking logger level configuration; the functional behavior appears unchanged. Should be triaged by whoever owns `nova_core/logging` setup.

---

## closed

### S311 per-file-ignores mechanism is inert under normal ruff check

**File**: root `pyproject.toml` — `[tool.ruff.lint.per-file-ignores] "apps/casino/**" = []`

**Problem**: S311 (no `import random`) sits in the root `[tool.ruff.lint] ignore` list, which applies globally. `per-file-ignores` is additive to `ignore` — it can only suppress additional rules for a path, never re-enable a globally-ignored rule. So `"apps/casino/**" = []` is inert: a plain `ruff check apps/casino/` still silently skips S311 even without this entry. The DoD gate (`ruff check apps/casino/ --select S311`) passes today only because casino code has no `import random` yet; the check doesn't actually prove the mechanism works for future casino code.

**Root cause**: The design that would work is the inverse: remove S311 from the global `ignore` list and add per-file-ignores entries for every *other* workspace member that legitimately needs it suppressed (`apps/bot/**`, `apps/server/**`, `tests/**`), leaving casino with no override so the default (S311 active) applies.

**Impact**: Medium — the code is correct today, but a future dev adding `import random` to casino code will not be caught by a default lint run. Only caught if someone explicitly runs `--select S311`.

**Fix**: Removed S311 from global `ignore`; added targeted per-file suppressions for `debug.py`, `hatching.py`, `logo_update.py`. Fixed in commit `21f631b` during phase 0.
