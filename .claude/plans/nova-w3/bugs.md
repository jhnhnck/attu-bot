# bugs — nova-w3

## open

- **lint-debt: RUF105 (noqa format) + PLW0717 (too-many-statements-in-try-clause)** — pre-existing codebase-wide pattern (47 RUF105 instances, 30+ PLW0717 across `apps/bot/`); carried into `nova_core/modlog/handlers.py` verbatim from `client/modlog.py`. not introduced by any nova-w3 phase. disposition: **defer** — standalone lint-cleanup pass; not a blocker for any downstream phase.
- **PLW0717 in events.py: `_restore_wiki_views` (18 stmts), `_do_ready_init` try blocks (7, 9 stmts)** — pre-existing ruff preview violations in `apps/bot/nova_core/client/events.py`; three `too-many-statements-in-try-clause` errors that predate phase 3. ruff --fix cannot auto-resolve these; would require extracting inner blocks. not a phase 3 regression. disposition: **defer** — same standalone lint-cleanup pass; not a blocker for any downstream phase.
- **design nit: `wire_wiki_command_repo` in repositories.py wires nova_core.commands.wiki** — creates a `nova_core.wiki.repositories` → `nova_core.commands` cross-module dep. eggs/ccboard keep this wiring in `__init__.py`. originally forced by the 30-line shim constraint; the 32-line overage is now accepted as the permanent floor, so the line-count driver is moot. disposition: **defer** — move wiring into `nova_core/wiki/__init__.py` in a future cleanup pass; low risk; not a blocker for any downstream phase.

## closed

(populated at phase close)
