# log — ccboard cutover prep

append-only. `phase-retro` and `plan-revise` write here during the loop.

## starting phase 0 — 2026-06-05

working directly in `.claude/worktrees/ccboard/` (branch `feat/ccboard`); no nested
worktree — this plan is a side plan inside an already-isolated worktree.

**confirmed dod:**
- `/stars leaderboard top-messages` returns a short "coming soon" message; no mention of
  ccboard, no hint of a feature flag.
- `GuildStarboard.enabled: bool = True` declared in `config.py`.
- `_starboard_enabled(guild_id) -> bool` in `events.py`; fails open (`except: return True`);
  guards all four legacy reaction handlers.
- roundtrip test: `enabled=False` survives save/load in `test_db_repositories.py`.
- unit tests: `_starboard_enabled` returns `False` when config has `enabled=False`; returns
  `True` on config-read exception.
- suite green.

## phase 0 retro — 2026-06-05

### spec delta
- delivered: all five dod items (coming-soon message, `GuildStarboard.enabled`, `_starboard_enabled()` helper + four guards, roundtrip test, unit tests for both helper paths).
- missed / deferred: none.
- extra: two existing tests asserted the old `'only available when ccboard is enabled'` string — updated both to `'coming soon'` as part of the message change. expected but not explicitly called out in the dod.

### surprises
- two test files (unit + component) contained the exact old error string → test baseline update required before suite was green. trivial fix but not anticipated in the dod text.
- `GuildStarboard` `valid_bots` is a mutable list default — pydantic handles it cleanly; no issue, just noted.

### residual debt
- none. all guards are additive; config field is backward-compatible; no workarounds accepted.

## starting phase 1 — 2026-06-05

working in `.claude/worktrees/ccboard/` (branch `feat/ccboard`); same slot as phase 0.

**confirmed dod:**
- guild config web UI has a "legacy starboard enabled" toggle in the starboard section.
- saving persists the value; loading the page reflects the persisted value.
- form, template, and js all wired.
- web roundtrip test: PATCH `starboard.enabled=false`, assert `config.guilds[id].starboard.enabled is False`.

## phase 1 retro — 2026-06-05

### spec delta
- delivered: all four dod items (forms.py enabled field, html toggle, js populateField,
  web roundtrip tests — two tests: enabled=False and enabled=True paths).
- missed / deferred: none.
- extra: added `enabled is True` assertion to the existing `test_default_values` in
  `TestGuildStarboardForm` (natural place since the default changed).

### surprises
- assets live under `apps/bot/legacy_web/` not at repo root — plan scope listed
  `assets/templates/` and `assets/static/js/`, actual paths are
  `apps/bot/legacy_web/templates/` and `apps/bot/legacy_web/static/js/`. trivial
  repath; no design impact.
- the starboard PATCH handler already does `GuildStarboard(**validated.model_dump())`
  so enabled flows through automatically once the form field exists — no route code
  needed beyond the form field.

### residual debt
- none.

## starting phase 2 — 2026-06-05

working in `.claude/worktrees/ccboard/` (branch `feat/ccboard`).

**gap audit decision:** step (b) is a short verification period; expected entry volume
is ~5-30 messages. per-entry `/fix ccboard purge <link>` is practical at that scale.
no bulk-purge command needed. phase 2 is doc-only.

**confirmed dod:**
- `notes/dev/ccboard-migration.md` covers all three steps with config, commands, expected
  outcome, and gaps.
- keep-vs-wipe decision documented; doc-only (no purge-guild command added).

## phase 2 retro — 2026-06-05

### spec delta
- delivered: `notes/dev/ccboard-migration.md` covering all three steps; keep-vs-wipe
  decision documented; gap audit decision (doc-only, no bulk-purge command).
- missed / deferred: none.
- extra: none.

### surprises
- nothing. phase was pure doc; no unknowns materialized.

### residual debt
- none. all three gaps called out in the pre-mortem (orphaned posts, display_message_ids
  orphan, bulk-purge tooling gap) are documented explicitly in the runbook.

## revision after phase 2 — 2026-06-05

- no downstream phases. all three phases closed. plan complete.

## revision after phase 1 — 2026-06-05

- phase 2 (migration runbook + gap audit): valid — no new gaps; spec unchanged.

## revision after phase 0 — 2026-06-05

- phase 1 (web ui toggle): valid — `GuildStarboard.enabled` field is now in place; web
  plumbing proceeds as drafted.
- phase 2 (migration runbook): valid — no new gaps discovered; spec unchanged.
