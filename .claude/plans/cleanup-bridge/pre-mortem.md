# pre-mortem — cleanup-bridge

**bottom line:** proceed with revisions (folded into plan before walk)

### risks

- [high] premise — sample toml (`config/attu-bot.sample.toml`) was at `2.5.4` with no `[bridge]` section; any fresh install or ci env copies from sample and fails on startup · resolved: fixed in phase 0 dod
- [high] premise — `test_logging.py` imports private symbols from `doom_bot.logging`; a shim approach would have broken them silently · resolved: phase 1 does a full migration and rewrites the test file
- [high] integration — `_bridge_started` flag race on rapid reconnects: moving flag to post-serve without a running-task reference allows two `_serve()` tasks to spawn · resolved: phase 0 fix uses running-task reference, not bool
- [medium] premise — webhook url source was unidentified before phase 1 was scoped · resolved: confirmed as `config.error_hook`; passed to `configure(webhook_url=config.error_hook)` at startup
- [medium] integration — uv workspace wiring for a new package (`attu-wiki`) is untested · resolved: walking skeleton probe required before moving any code in phase 2
- [low] dependency — `msgpack`, `idna`, `pip` dependabot alerts are transitive/build-tool; not ours to fix directly · documented in phase 3 dod

### walking-skeleton check

phase 0 is pure bug fixes — no new infrastructure, no skeleton needed. phase 2 adds the first new workspace package; walking skeleton probe (package skeleton + `uv sync`) is required before moving code, per phase 2 dod.

### phase-order revisions

none — 0 → 1 → 2 → 3 is correct.

### definition-of-done additions

all additions folded into plan.md before the phase walk.
