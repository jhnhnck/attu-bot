# bugs — nova-w3

## open

- **lint-debt: RUF105 (noqa format) + PLW0717 (too-many-statements-in-try-clause)** — pre-existing codebase-wide pattern (47 RUF105 instances, 30+ PLW0717 across `apps/bot/`); carried into `nova_core/modlog/handlers.py` verbatim from `client/modlog.py`. not introduced by any nova-w3 phase. disposition: **defer** — plan-wide residual; no downstream phase will absorb this; open a standalone lint-cleanup task if desired.
- **PLW0717 in events.py: `_restore_wiki_views` (18+ stmts), `_do_ready_init` try blocks (7, 9 stmts)** — pre-existing ruff preview violations in `apps/bot/nova_core/client/events.py`; three `too-many-statements-in-try-clause` errors that predate phase 3. confirmed unchanged by phase 6 -- starboard removal did not enter any of the flagged try blocks; statement counts unaffected. ruff --fix cannot auto-resolve these; would require extracting inner blocks. disposition: **defer** — plan-wide residual; no downstream phase will absorb this; same standalone lint-cleanup task as above.
- **design nit: `wire_wiki_command_repo` in repositories.py wires nova_core.commands.wiki** — creates a `nova_core.wiki.repositories` -> `nova_core.commands` cross-module dep. eggs/ccboard keep this wiring in `__init__.py`. originally forced by the 30-line shim constraint; the 32-line overage is now accepted as the permanent floor, so the line-count driver is moot. disposition: **defer** — plan-wide residual; low risk; a single cleanup commit in a future session can move the wiring into `nova_core/wiki/__init__.py`; no plan needed.
- **lint-debt: rule-codes-in-selectors (pyproject.toml)** — ruff now requires rule names (e.g. `isort`) instead of codes (e.g. `I001`) in `lint.ignore` and `lint.per-file-ignores`; 28+ violations across `pyproject.toml` lint config blocks. pre-existing; none introduced by nova-w3. disposition: **defer** — plan-wide residual; no downstream phase will absorb this; a standalone pyproject.toml update pass is needed.
- **lint-debt: RUF103 invalid suppression comments + S108/PLR0915/PLW0603/S105 across events.py, wiki/__init__.py, test_wiki_http.py** — confirmed still present: `events.py` lines 28 and 102 use `# ruff: ignore[...]` syntax (RUF103); `wiki/__init__.py` lines 15 and 29 use `# ruff: ignore[...]` syntax (RUF103). none introduced by any nova-w3 phase. disposition: **defer** — plan-wide residual; no downstream phase will absorb this; same standalone lint-cleanup task.

## closed

(populated at phase close)
