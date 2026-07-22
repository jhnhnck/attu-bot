# pre-mortem — nova-w3

**Bottom line:** proceed with revisions

---

### risks

- [high] premise — repo injection mechanism is nova-w2's concern, not documented here; if the loader injects repos into feature module-level singletons differently than the existing `_wire_repos()` pattern (e.g., factory method vs. direct attribute assignment), phase 0 scope collapses on day one · probe: read nova-w2 plan/spec before writing phase 0 code; confirm exactly how `repository_classes` in the manifest gets instantiated and wired into feature module singletons; document the pattern in phase 0 scope before coding starts

- [medium] integration — `_restore_wiki_views` in `client/events.py` is a startup hook, not a Discord event; the manifest `event_handlers` dict is keyed on Discord event names, so there is no slot for a startup callback; either nova-w2 added a `startup` field to `FeatureManifest` or the wiki restore logic stays in `client/events.py` as a non-manifest call · probe: check nova-w2 plan/spec for a `startup` or `on_ready` manifest field before drafting phase 3 scope; if absent, adjust phase 3 to keep `_restore_wiki_views` in events.py with a shim import from `doom_bot.wiki`

- [medium] premise — the plan says each phase removes feature classes from `attu_models` and updates `doom_bot/database/__init__.py`; these are the same two files touched in every phase, making every phase a potential merge conflict with any unmerged sibling branch; the sequential gate (each phase closes before the next starts) mitigates this, but the constraint must be held strictly · probe: confirm with the team that no parallel nova-w3 branch work occurs; add an explicit note in the merge gate for phase 1 onward that `attu_models/__init__.py` and `doom_bot/database/__init__.py` must be at HEAD before coding starts

- [medium] scope — `FeatureManifest.migrations` field: `doom_bot/ccboard/migration.py` contains migration logic; the manifest design shows `migrations=[...]` but the nova-w2 loader's behavior with per-feature migrations (order, idempotency, schema version bump) is unspecified here; if nova-w2 didn't implement the migrations field, phase 1 will need to keep `migration.py` wired through the existing path · probe: check nova-w2 spec for `migrations` field implementation before phase 1; if unimplemented, remove from phase 1 scope and note as nova-w2 follow-up

- [low] integration — `on_member_join` is handled in both `client/events.py` (welcome message) and `client/modlog.py` (modlog embed); when modlog becomes manifest-driven, the loader registers a second `bot.listen()` for `on_member_join`; pycord supports multiple listeners on the same event so this is safe, but the plan should note the dual-handler pattern explicitly to avoid confusion · probe: none needed; note in phase 2 scope that `on_member_join` has two handlers after migration

- [low] dependency — `packages/attu-wiki` will need `httpx` or `aiohttp` for wiki http calls (currently available transitively through the bot package); after extraction the package must declare its own deps in `pyproject.toml`; missing dep declarations will only surface on a clean install · probe: check `doom_bot/wiki/client.py` imports before starting phase 3 skeleton; list all stdlib vs. third-party deps that need to move into `packages/attu-wiki/pyproject.toml`

- [low] scope — goal 5 says "no doom_bot.tasks.__init__.py or client/events.py edits required to add or remove a feature after phase 0" but the very first act of nova-w3 (phase 0) includes editing both those files to remove eggs registration; the goal should read "after phase 0 closes, the remaining phases require no edits to those files" — this is fine but the wording in goals needs tightening to avoid a false DoD check at phase 0

---

### walking-skeleton check

**verdict:** phase 0 (eggs) is a genuine walking skeleton. it touches every layer: document move, repo move, manifest declaration, task wiring via manifest, command wiring via manifest, attu_models shrink, doom_bot/database/__init__.py shrink, import site updates across commands/ and tasks/. every subsequent phase repeats the same layer set. the one missing element is the startup-hook layer (wiki introduces this in phase 3); no change needed here since the modlog phase (phase 2) validates event-only manifests first.

the nova-core.md contract explicitly calls eggs the template phase, so no walking-skeleton reordering is warranted.

---

### phase-order revisions

| original | proposed | reason |
|---|---|---|
| (all phases) | no change | specified order matches uncertainty profile; ccboard is highest-complexity data migration (correct to do early); modlog proves event-only pattern before wiki introduces the startup-hook ambiguity; reminders/trees/starboard are decreasing complexity |

---

### definition-of-done additions

- phase 0 — add: "nova-w2 repo injection mechanism documented and confirmed before coding starts (see pre-mortem high risk)"; add: "with eggs removed from toml `[features].enabled`, the bot starts without `_egg_repo`, `_egg_user_repo` wired, and no eggs-related index init runs (confirm via startup log)"
- phase 1 — add: "with ccboard removed from toml `[features].enabled`, no ccboard event handlers fire (confirm via test or manual startup log — no `registered: doom_bot.ccboard` in output)"; add: "migration.py wiring confirmed via nova-w2 spec before coding starts (see pre-mortem medium risk)"
- phase 2 — add: "note in scope that on_member_join has two active handlers after migration (welcome message in events.py, modlog embed via manifest); both must fire in tests"
- phase 3 — add: "packages/attu-wiki/pyproject.toml lists all third-party deps (confirm via `uv sync` on a clean virtualenv after skeleton step, before any code moves)"; add: "`_restore_wiki_views` startup hook placement confirmed against nova-w2 spec before coding starts (see pre-mortem medium risk)"
- phase 6 — add: "attu_models contains no feature-specific classes (grep check: no Egg, Reaction, Entry, Family, Reminder, WikiView, StarredMessage in attu_models/documents.py and attu_models/repositories.py)"
