# nova-w4 — bug log

<!-- bug-triage appends here -->

## open

### S311 per-file-ignores mechanism is inert under normal ruff check

**File**: root `pyproject.toml` — `[tool.ruff.lint.per-file-ignores] "apps/casino/**" = []`

**Problem**: S311 (no `import random`) sits in the root `[tool.ruff.lint] ignore` list, which applies globally. `per-file-ignores` is additive to `ignore` — it can only suppress additional rules for a path, never re-enable a globally-ignored rule. So `"apps/casino/**" = []` is inert: a plain `ruff check apps/casino/` still silently skips S311 even without this entry. The DoD gate (`ruff check apps/casino/ --select S311`) passes today only because casino code has no `import random` yet; the check doesn't actually prove the mechanism works for future casino code.

**Root cause**: The design that would work is the inverse: remove S311 from the global `ignore` list and add per-file-ignores entries for every *other* workspace member that legitimately needs it suppressed (`apps/bot/**`, `apps/server/**`, `tests/**`), leaving casino with no override so the default (S311 active) applies.

**Impact**: Medium — the code is correct today, but a future dev adding `import random` to casino code will not be caught by a default lint run. Only caught if someone explicitly runs `--select S311`.

**Fix scope**: Cross-cutting change to root `pyproject.toml` and potentially other workspace member lint configs. Out of scope for nova-w4 phase 0; should be addressed before nova-w2 (feature loader) which is most likely to introduce `random` usage.
