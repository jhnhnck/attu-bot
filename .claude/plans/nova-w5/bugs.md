# nova-w5 bugs

## open

- **bridge fix endpoint missing** — `POST /bridge/fix/recalculate-starboard` does not exist in `doom_bot/bridge/router.py`. the `fix.py` admin endpoint ships with a `501` fallback until this lands. tracked here so `bug-triage` can promote it to a real bridge task when phase 3 merges. severity: medium (feature incomplete, not broken). disposition: deferred to nova-w3 or a standalone bridge task.

## closed
