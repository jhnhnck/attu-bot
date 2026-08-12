# bugs — nova-w3

## open

- **lint-debt: RUF105 (noqa format) + PLW0717 (too-many-statements-in-try-clause)** — pre-existing codebase-wide pattern (47 RUF105 instances, 30+ PLW0717 across `apps/bot/`); carried into `nova_core/modlog/handlers.py` verbatim from `client/modlog.py`. not introduced by any nova-w3 phase. disposition: defer to standalone lint-cleanup pass; not a blocker for any downstream phase.

## closed

(populated at phase close)
