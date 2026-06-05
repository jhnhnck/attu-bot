# pre-mortem — ccboard cutover prep

adversarial review of all three phases before any code is written. conducted 2026-06-04.

---

## risks table

| # | risk | sev | phase | mitigation |
|---|---|---|---|---|
| 1 | `_starboard_enabled` accidentally fails closed — legacy silenced on any config error | high | 0 | `except: return True`; unit test covers both the False path and the exception path |
| 2 | no starboard-enabled roundtrip test → field silently dropped on save (same failure mode as bug #2 in ccboard plan) | medium | 0 | DoD requires adding roundtrip test before phase 0 closes |
| 3 | web UI JS nested-field path typo → toggle silently stays checked on page load | medium | 1 | mirror `ccboard.enabled` JS pattern exactly; web roundtrip test catches it |
| 4 | `_sync_post` channel-change self-heal path (`discord.NotFound` → clear ref → recreate) unverified in test suite | low | 2 | confirmed by code reading at `manager.py:179-184`; step-(b) live smoke check exercises it |
| 5 | orphaned posts in testing guild's channel not auto-cleaned by `cleanup_orphans` after channel move | low | 2 | `cleanup_orphans` scans `cfg.channel_id` (current channel only); manual deletion required; explicitly called out in runbook |
| 6 | step-(b) `display_message_ids` entries contain testing-channel message ids after migration | nit | 2 | harmless — redirect lookups just miss; noted in runbook |
| 7 | bulk-purge tooling gap if wipe-vs-keep decision favors wipe and entry volume is large | low | 2 | phase 2 audits the volume; adds `/fix ccboard purge-guild` if needed |

---

## walking skeleton verdict

phase 0 touches four distinct layers:
- `stars.py` — command (slash command surface)
- `config.py` — model (pydantic config layer)
- `events.py` — event handler (reaction routing)
- tests — both unit and component

this proves the config-read-to-event-gate seam before phase 1 adds web UI risk. phase 0 is
the correct skeleton. no phase 0 rework needed.

---

## phase order verdict

- phase 0 first: trivial risk, proves the seam, establishes the field.
- phase 1 second: web UI is the highest unknown (js field path, html toggle pattern).
- phase 2 last: doc-only with a conditional code addition; no unknowns that block phase 0/1.

order is correct. no reorder needed.

---

## dod additions

applied inline in `plan.md`:

- phase 0: roundtrip test + unit tests for both `_starboard_enabled` paths (added to DoD).
- phase 1: web roundtrip test (added to DoD).
- phase 2: explicit keep-vs-wipe decision + volume check for bulk-purge gap (added to DoD).

---

## runbook content (reference for phase 2 author)

the `notes/dev/ccboard-migration.md` file must cover:

### step (a) — secondary/testing guild, fresh start

- configure in web UI: `ccboard.enabled=True`, `ccboard.channel_id`, `ccboard.emojis`,
  `ccboard.threshold`, `ccboard.points_label`.
- do NOT run `/fix stars convert` — starts with empty `ccboard_reactions` and
  `ccboard_entries`.
- verification checklist: react with the configured emoji to a text message, image message,
  reply message, and sticker. confirm bot posts appear in the ccboard channel with correct
  embeds. check the bot's own reaction on the post (lowest positive emoji).

### step (b) — primary guild, cross-guild verification

- set `ccboard.channel_id` on the primary guild to the **testing guild's** channel id.
- operational note: `bot.get_channel(id)` in py-cord 2.x uses a flat channel cache
  regardless of guild; cross-guild posting works as long as the bot is in both guilds.
- new reactions on the primary guild accumulate in `ccboard_reactions` keyed to primary's
  `guild_id`; posts appear in the testing guild's channel.
- verification: pick a message that also has a legacy starboard post; compare the ccboard
  embed with the legacy embed. check image, reply context, content string format.
- note: `display_message_ids` on entries created during this period point to testing-channel
  message ids; after migration these ids are orphaned but harmless (redirect lookups miss
  silently).

### step (c) — cutover

**keep-vs-wipe decision**
- *keep*: step-(b) reactions are real user data; keep them. `regen` + channel move causes
  manager to recreate all posts in the new channel on next tick.
- *wipe*: clear test-period entries before going live. per-entry `/fix ccboard purge <link>`
  is the current path; if volume makes that impractical, use `/fix ccboard purge-guild`
  (added in phase 2 if needed).

**cutover steps (keep path)**
1. `/fix ccboard regen` — marks all primary guild entries `is_dirty=True`.
2. change `ccboard.channel_id` to the primary guild's real ccboard channel in web UI.
3. wait for manager tick (≤70s). `_sync_post` attempts to edit old post in testing channel:
   - `channel = bot.get_channel(new_channel_id)` — points to the primary channel.
   - `channel.get_partial_message(old_starboard_message_id)` — partial message with old id
     in new channel.
   - `await existing.edit(...)` → `discord.NotFound` (old id not in new channel).
   - handler at `manager.py:179-184`: clears `starboard_message_id`, calls `_create_post`.
   - new post appears in the primary channel. ✓
4. flip `starboard.enabled = False` in web UI. legacy starboard silenced for this guild.

**post-cutover cleanup**
- orphaned posts in the testing guild's channel (bot-authored posts from step b): these
  are NOT found by `cleanup_orphans` because that command scans `cfg.channel_id` (now the
  primary channel). manual deletion required: go to the testing channel and delete the bot's
  posts, or use the testing guild's `cleanup_orphans` if the testing guild's ccboard is
  still configured to that channel.
- entries from the secondary guild (step a): disable ccboard on the secondary guild
  (`ccboard.enabled=False`); optionally purge test entries via `/fix ccboard purge <link>`
  per entry or `/fix ccboard purge-guild confirm:True` if that command was added.

---

## bottom line

plan is safe to proceed as drafted. no rework needed before phase 0.
