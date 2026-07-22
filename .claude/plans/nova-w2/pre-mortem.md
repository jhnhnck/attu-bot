# pre-mortem - nova-w2: feature manifest system

**bottom line:** proceed with revisions: two corrections applied before plan closed; no rework required. one high risk fixed in plan, one high risk scheduled into phase 0 as a probe.

---

### risks

- [high] integration: `bot.listen()` when called programmatically as a non-decorator may not behave as expected; the calling convention `bot.listen()(handler_fn)` vs `bot.add_listener(handler_fn, name='on_message')` is unverified · probe: phase 0 walking skeleton registers the synthetic `on_message` handler via `bot.listen()(handler_fn)` and asserts it fires in a unit test; if it raises or silently drops, substitute `bot.add_listener()` and document the substitution before merge

- [high] premise: initial draft placed the loader in `start_bot_loop()` (sync, before bot loop starts); correct placement is `_do_ready_init()` after `init_database()` so document/repo wiring runs with a live db connection; nova-w3 merge gate explicitly requires "FeatureManifest, FeatureContext, loader live in client/events.py on_ready" · **corrected in plan before phase 0**: phase 0 scope and DoD both specify `_do_ready_init()` placement

- [medium] premise: repo injection mechanism unspecified: nova-w3 pre-mortem explicitly flags this as high risk ("repo injection mechanism … must be confirmed against the nova-w2 spec before phase 0 coding starts"); the current codebase wires repos via module-level singletons in `doom_bot/database/__init__.py`; the manifest-driven equivalent is not yet designed · probe: phase 1 scope requires implementing and documenting the chosen pattern (two candidates: loader calls `feature_module.init_repos(db)` function if present; or loader instantiates `repository_classes` and injects via a feature-scoped registry); the pattern must be specific enough for nova-w3 phase 0 to cite

- [medium] scope: base package extraction effort unknown before phase 2: ping is an inline `@discord.slash_command` decorator in `client/__init__.py`; making it a callable `setup` fn for `BasePackageSpec` requires extraction; bridge-health location is unknown · probe: pre-phase audit table (6 rows: name, current location, extraction cost) produced before any phase 2 code is written; items rated "significant move" escalated before continuing

- [low] integration: extension name collision: if a manifest `setup(bot)` calls `bot.load_extension()` with a path that collides with a pkgutil-discovered extension, pycord may raise on the duplicate · probe: confirm the synthetic `/manifest-ping` extension (`nova_core.features._test_feature`) loads cleanly alongside existing `nova_core.commands.*` extensions in the walking skeleton test

- [low] premise: `startup` field not in contract: nova-w3 asks whether `FeatureManifest` has a `startup: Callable | None` field for per-feature post-ready hooks (`_restore_wiki_views`); the contract's manifest example does not include it · probe: phase 1 resolves and documents the decision; nova-w3 phase 3 merge gate cites the resolution

---

### walking-skeleton check

**verdict: valid.** phase 0 exercises all hook types (task, event handler, slash command). empty `document_classes` and `repository_classes` are acceptable in phase 0: `_wire_documents` and `_wire_migrations` methods exist and are called; they are no-ops on empty lists. the repo injection design question defers cleanly to phase 1 because the synthetic feature has no repos. the critical loader placement correction is reflected in the plan.

---

### phase-order revisions

| original | proposed | reason |
|---|---|---|
| phase 0 loader wired in `start_bot_loop()` | phase 0 loader wired in `_do_ready_init()` after `init_database()` | db connection required for document/repo wiring; nova-w3 merge gate depends on this location |

no other reordering needed. phase 0 (walking skeleton) → phase 1 (full API + TOML) → phase 2 (base package) is already risk-first.

---

### definition-of-done additions

- phase 0: add: `bot.listen()` programmatic pattern confirmed; if substituted with `bot.add_listener()`, note the substitution in the commit message
- phase 0: add: `grep -n 'FeatureContext\|load_base\|load_all' nova_core/client/events.py` shows all three calls inside `_do_ready_init()`, after the `await init_database(...)` line
- phase 1: add: repo injection mechanism implemented and documented with enough specificity that nova-w3 phase 0 gate can confirm it; decision noted in `notes/nova-core.md` feature manifest design section
- phase 1: add: `startup` field decision documented with rationale; nova-w3 phase 3 merge gate cites the outcome
- phase 2: add: pre-phase audit table for all 6 base items produced before writing any code; any item rated "significant move" escalated and approved before continuing
