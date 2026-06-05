# ccboard migration

three-step process for cutting over from the legacy starboard to ccboard on the primary guild. the steps are intentionally manual and per-guild. do not skip or reorder them.

---

## step (a) — secondary/testing guild, fresh start

**purpose:** verify ccboard embed output before touching the primary guild at all.

### configure in the web ui

- `ccboard.enabled = True`
- `ccboard.channel_id` — the channel where board posts will appear
- `ccboard.emojis` — set weights (e.g. `⭐: 1`)
- `ccboard.threshold` — minimum points to post (e.g. `2`)
- `ccboard.points_label` — display label (e.g. `stars`)

do **not** run `/fix stars convert`. the testing guild starts with empty `ccboard_reactions`
and `ccboard_entries` — a clean slate is the point.

### verification checklist

react to each of these message types with the configured emoji:

- plain text message
- message with an image attachment
- reply (ensure reply context appears in the embed)
- sticker (verify the embed handles sticker-only content without crashing)

for each, wait for the board post to appear (manager tick is ≤60s settle + ≤10s poll =
≤70s). confirm:

- embed appears in the correct channel
- bot adds its own lowest-positive-emoji reaction to the post
- embed content, image, and author match the source message
- points count is correct

---

## step (b) — primary guild, cross-guild verification

**purpose:** confirm new reactions on the primary guild produce correct board embeds,
using the testing guild's channel as a safe output channel.

### configure in the web ui (primary guild)

- `ccboard.enabled = True`
- set `ccboard.channel_id` to the **testing guild's** board channel id

**note:** `bot.get_channel(id)` in py-cord 2.x uses a flat channel cache regardless of
guild; cross-guild posting works as long as the bot is in both servers.

### what happens

- new reactions on primary guild messages accumulate in `ccboard_reactions` keyed to the
  primary guild's `guild_id`.
- board posts appear in the testing guild's channel where you can inspect them side-by-side
  with the legacy starboard posts.

### verification

pick a message that also has a legacy starboard post and react to it. compare:

- embed image matches the legacy starboard embed
- author, content, and reply context render correctly
- points label and color match config

also verify the legacy starboard **still fires** for the same reaction (the
`_starboard_enabled` guard defaults to `True`, so both systems are active).

### known side effect

`display_message_ids` on entries created during step (b) point to the testing guild's
channel message ids. after the channel move in step (c), these ids are orphaned. this is
harmless — redirect lookups miss silently and the posts themselves will be recreated in
the primary channel by `regen`.

---

## step (c) — cutover

### keep-vs-wipe decision

decide whether to keep or discard entries accumulated during step (b).

**keep** (recommended default)
- step (b) reactions are real user data. regen + channel move causes the manager to
  recreate all posts in the new channel on the next tick.
- orphaned testing-channel post ids in `display_message_ids` are harmless.

**wipe**
- use if you want a clean slate in production (e.g. step (b) period was noisy).
- current tooling: per-entry `/fix ccboard purge <message_link>`. at expected
  verification-period volume (~5-30 entries) this is practical.
- there is no guild-wide bulk-purge command; if volume turns out to be much higher than
  expected, stop here and add one before proceeding.

### cutover steps (keep path)

1. run `/fix ccboard regen` on the primary guild — marks all entries `is_dirty=True`.

2. in the web ui, change `ccboard.channel_id` on the primary guild to the **primary
   guild's real ccboard channel** (not the testing channel).

3. wait for the manager tick (≤70s). on each dirty entry, `_sync_post` attempts to edit
   the old post via `channel.get_partial_message(old_id)` on the new channel →
   `discord.NotFound` → clears `starboard_message_id` → calls `_create_post`. new posts
   appear in the primary channel. (confirmed path: `manager.py:179-184`.)

4. in the web ui, set `starboard.enabled = False` on the primary guild. the legacy
   starboard stops firing for this guild; ccboard is now the sole reaction board.

### cutover steps (wipe path)

before step 2, purge test-period entries one at a time:

```
/fix ccboard purge <message_link>
```

repeat for each entry accumulated during step (b). once the database is clean, follow
steps 2-4 from the keep path above.

### post-cutover cleanup

**orphaned posts in the testing guild's channel**

bot-authored posts from step (b) remain in the testing guild's channel after the channel
move. `cleanup_orphans` will **not** find them — it scans `cfg.channel_id` (now the
primary channel). manual deletion required:

- go to the testing guild's board channel and delete the bot's posts, or
- run `/fix ccboard cleanup-orphans` on the testing guild while its ccboard is still
  pointed at that channel, then disable ccboard on the testing guild.

**testing guild cleanup**

set `ccboard.enabled = False` on the secondary/testing guild. optionally purge test
entries via `/fix ccboard purge <link>` per entry.
