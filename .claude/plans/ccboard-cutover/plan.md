# ccboard cutover prep

three concerns bundled because they all gate the same migration event. branch `feat/ccboard`
(worktree `.claude/worktrees/ccboard`).

## goals

- `/stars leaderboard top-messages` shows a generic "coming soon" message so non-enabled
  guilds see no hint of an unreleased feature toggle.
- `GuildStarboard.enabled: bool = True` (tier-3) added so the legacy starboard can be
  silenced per-guild via the web UI without removing any code.
- an operational migration runbook exists covering all three migration steps end-to-end,
  with every known gap called out explicitly.

## non-goals

- removing or deprecating legacy starboard code.
- automating the migration — intentionally manual, per-guild.
- changing any ccboard behavior other than the starboard event gate.
- running the migration itself (this plan prepares only).

## constraints

- worktree `.claude/worktrees/ccboard`, branch `feat/ccboard`. commits land there.
- no push, no deploy, no discord interaction without explicit instruction.
- `GuildConfigDocument.starboard` is `dict = {}` in `documents.py:28`, unpacked as
  `GuildStarboard(**doc.starboard)` at `config.py:632`. adding `enabled: bool = True` to
  `GuildStarboard` is backward-compatible — existing documents without the field use the
  pydantic default. no DB model change needed.
- dev worktree's uncommitted `events.py` WIP (bug #12 in the ccboard plan) produces a
  merge conflict at the ship gate. same class as existing ccboard edits; deferred.

## accepted risks

three risks surfaced in [pre-mortem.md](pre-mortem.md) and mitigated by design:
(1) `_starboard_enabled()` uses `try/except: return True` (fail open — legacy fires on
any config error, never silently suppressed; contrast with `_ccboard_enabled` which fails
closed). (2) the `_sync_post` channel-change self-heal path (`edit → discord.NotFound →
clear ref → recreate`) is confirmed by code reading at `manager.py:179-184` but
unexercised in tests — documented in the runbook; the step-(b) live smoke check exercises
it. (3) orphaned posts in the testing guild's channel after migration are not auto-cleaned
by `cleanup_orphans` (which scans only the current `cfg.channel_id`) — manual deletion
step; called out in the runbook.

## phase 0 — cosmetic fix + `starboard.enabled` event gate

**status:** pending merge

**definition of done:**
- `/stars leaderboard top-messages` returns a short "coming soon" message; no mention of
  ccboard, no hint of a feature flag.
- `GuildStarboard.enabled: bool = True` declared in `config.py`.
- `_starboard_enabled(guild_id) -> bool` helper in `events.py`; mirrors `_ccboard_enabled`;
  fails open (`except: return True`); guards all four legacy reaction handlers; default
  `True` means zero behavior change from today.
- roundtrip test: `enabled=False` persists through save/load. added alongside
  `test_ccboard_roundtrip` in `tests/python/component/test_db_repositories.py`.
- unit tests: `_starboard_enabled` returns `False` when config has `enabled=False`; returns
  `True` on config-read exception.
- suite green.

**scope:**
- `apps/bot/doom_bot/commands/stars.py` — one-line message change in `stars_top_messages`
- `apps/bot/doom_bot/config.py` — `enabled: bool = True` on `GuildStarboard`
- `apps/bot/doom_bot/client/events.py` — `_starboard_enabled()` helper + four guards
- `tests/python/unit/` — unit tests for `_starboard_enabled`
- `tests/python/component/test_db_repositories.py` — starboard-enabled roundtrip test

**rollback:** revert only the four guards in `events.py`; config field is additive/safe to
leave. tests stay.

## phase 1 — web UI toggle for `starboard.enabled`

**status:** pending merge

**definition of done:**
- guild config web UI has a "legacy starboard enabled" toggle in the starboard section.
- saving persists the value; loading the page reflects the persisted value.
- form, template, and js all wired.
- web roundtrip test: POST `starboard.enabled=false`, reload, assert False.

**scope:**
- `apps/bot/doom_bot/web/forms.py` — `enabled` bool field on the starboard form section
- `assets/templates/guild_config.html` — toggle in the starboard block; mirror the
  existing `ccboard.enabled` toggle HTML pattern exactly
- `assets/static/js/app.js` — `populateField` / field assignment for
  `data.starboard.enabled` in `loadGuildConfig()`; follow the `ccboard.enabled` js path
- tests: web roundtrip (save False, reload, assert)

**rollback:** wrong js key path → toggle silently stays checked on reload; fix the path.

## phase 2 — migration runbook + gap audit

**status:** pending merge

**definition of done:**
- `notes/dev/ccboard-migration.md` exists and covers all three steps with config, commands,
  expected outcome, and gaps (see spec in [pre-mortem.md](pre-mortem.md) under "runbook
  content").
- keep-vs-wipe decision documented. if per-entry purge is impractical for expected volume,
  `/fix ccboard purge-guild [confirm]` added to `commands/fix.py`; otherwise doc-only.

**scope:**
- `notes/dev/ccboard-migration.md` (new file)
- `apps/bot/doom_bot/commands/fix.py` only if bulk-purge gap is confirmed

**rollback:** doc-only; code only if tooling gap is confirmed.
