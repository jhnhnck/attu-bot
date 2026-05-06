# Starboard

Reference for the starboard feature - behavior rules, embed structure, config, and code pointers.

---

## Configuration

Configured per-guild in MongoDB under `starboard`:

| Field | Type | Purpose |
|---|---|---|
| `channel_id` | `int` | ID of the starboard channel |
| `emojis` | `dict[str, str]` | maps emoji string to hex color (e.g. `{'⭐': '#EEDD20'}`) |
| `valid_bots` | `list[int]` | bot IDs whose reactions are ignored (legacy ingress bots) |

Only emojis listed in `emojis` are tracked. Any other reaction is silently ignored.

---

## Behavior Rules

- any user can star any message with a configured emoji
- self-stars don't count (reactor == message author)
- bot reactions are ignored (own bot + `valid_bots`)
- each user gets **one vote per message** - their first reaction counts; subsequent reactions with different emojis are auto-removed from discord; no double counting across emojis
- messages in the starboard channel itself are also eligible to be starred; the bot redirects those reactions to the original message record
- a post is created once any single emoji reaches a weighted count of **2** (requires at least 2 different users reacting with the same emoji, or 1 super + 1 normal on the same emoji)
- a starboard post is deleted if reactions drop below threshold; the reference is cleared so a new post can be created if reactions recover
- if all reactions on a message are cleared (e.g. by a moderator), the bot clears the reaction state and deletes the starboard post if it exists
- if all reactions of a single emoji are cleared, that emoji is removed from the record and the post is updated or deleted as appropriate
- the bot reacts to its own starboard post with all active emojis
- if the starboard post was created by an old bot (can't edit it), the bot sends a reply with the updated content and tracks that as the new post
- if a starboard post is deleted externally, the reference is cleared so a new post can be created next time the count changes
- a star should only ever be removed when explicitly received as a reaction remove event
- when the bot removes a reaction (self-star, duplicate cleanup), it registers the removal in `_pending_bot_removals` so the echoed `on_raw_reaction_remove` event from discord is ignored and does not decrement legitimate votes
- a reaction on the response to a /star random or /star lost command should count towards the message it refers to.

---

## Post Format

### Content string

```
⭐ **4** | 🌟 **1.5** | https://discord.com/channels/<guild>/<channel>/<message>
```

- only emojis with at least one reaction are listed
- sorted by weighted count descending
- counts are shown as integers when whole (e.g. `4`), decimals when fractional (e.g. `1.5`)
- jump url is always last

### Embed color

color comes from the emoji in `emojis` with the highest count. falls back to `0xEEDD20` (gold) if none match.

### Embed structure by message type

**standard text message** - one embed:
- `author.name` - sender display name; `author.url` - jump link; `author.icon_url` - sender avatar
- `description` - message text
- `timestamp` - original message timestamp

**message with image** - same as above plus `image.url` from the first attachment; `description` omitted if no text

**multiple images** - first embed has author + description + first image; each additional image is a separate embed with only `image.url`

**reply message** - two embeds:
1. quoted/replied-to message: `color = 0x2B2D31` (discord dark background), `author.name = "Replying to <name>"`, `author.url` = link to referenced message; `description` = referenced content; first attachment as `image` if present
2. the starred message: normal author + description + color from dominant emoji

**link preview** - if the message has no content but has stored embeds, the first embed's description/url/fields are merged onto the main embed unless the embed contains richer metadata (title, fields, author, footer) in which case it is rendered as a second embed

**stored embed hydration** - the stored embed blob now preserves `title`, `description`, `url`, `color`, `image_url`, `thumbnail_url`, `fields`, `footer`, `author`, and `timestamp`. When the original message already included text or attachments, we merge only the description/url/image unless the stored embed is more complex, in which case the hydrated embed is pushed as a secondary embed so the full structured payload survives in the starboard post.

**forwarded message** - same as a standard text/image embed but with a footer set to `"forwarded message"`; content, attachments, and embeds are sourced from `message.snapshots[0].message` (a `ForwardedMessage`) rather than the forwarding message itself, which has no content of its own

**attachment heuristics** - attachments lacking a Discord `content_type` are now detected by filename/URL extensions (`.png`, `.jpg`, `.gif`, etc.) so images still surface on the starboard when Discord omits the MIME type.

---

## Key Functions (`apps/bot/doom_bot/client/starboard.py`)

| Function | Purpose |
|---|---|
| `handle_star_add(guild_id, channel_id, message_id, user_id, emoji_str, is_burst)` | entry point for `on_raw_reaction_add` |
| `handle_star_remove(guild_id, channel_id, message_id, user_id, emoji_str, is_burst)` | entry point for `on_raw_reaction_remove` |
| `handle_star_clear(guild_id, channel_id, message_id)` | entry point for `on_raw_reaction_clear` (all emojis cleared) |
| `handle_star_clear_emoji(guild_id, channel_id, message_id, emoji_str)` | entry point for `on_raw_reaction_clear_emoji` (single emoji cleared) |
| `_fetch_store_and_backfill(guild_id, channel_id, message_id, guild_config)` | fetches a message from discord, stores it, and backfills all existing reactions |
| `build_content(reactions, jump_url, emoji_colors, super_reactions)` | builds the content string |
| `dominant_color(reactions, emoji_colors, fallback, super_reactions)` | returns the color int for the highest weighted-count emoji |
| `build_embeds(message_doc, guild_id, color)` | builds the full embed list for a starred message |
| `parse_starboard_content(content)` | parses a legacy content string into `(emoji_counts, jump_url)` |
| `parse_jump_url(url)` | extracts `(guild_id, channel_id, message_id)` from a jump url |
| `backfill_message_reactions(message, guild_id)` | processes all existing reactions on a message for backfill |
| `_sync_starboard_post(guild_id, doc, guild_config)` | creates or updates the starboard channel post |

---

## Commands

| Command | Purpose |
|---|---|
| `/stars random` | random message with 2+ stars |
| `/stars lost` | random message with exactly 1 star |
| `/stars recheck <link>` | force-update the starboard post for a specific message |
| `/stars most-stars` | leaderboard - top users by stars received |
| `/stars most-starred` | leaderboard - top users by messages on the starboard |
| `/stars most-given` | leaderboard - top users by stars given |
| `/fix starboard recover [days]` | scan the starboard channel for bot posts and restore missing db records or fix broken links (default 7 days) |
| `/fix starboard recount` | re-fetch live discord reactions for all starred messages and rebuild reaction lists |
| `/fix starboard regen` | rebuild every starboard post for this guild |
| `/fix starboard purge <message_link>` | remove a message from the starboard db (and delete its discord post if possible) |

---

## Storage (`StarboardRepository`)

document: `StarredMessageDocument`

| Field | Type | Purpose |
|---|---|---|
| `message_id` | `int` | original message id (primary key) |
| `channel_id` | `int` | original channel |
| `guild_id` | `int` | guild |
| `author_id` | `int` | message author |
| `starboard_message_id` | `int \| None` | linked starboard post id |
| `reactions` | `dict[str, list[int]]` | emoji -> list of user ids who normal-reacted (1.0x weight) |
| `super_reactions` | `dict[str, list[int]]` | emoji -> list of user ids who super-reacted (1.5x weight) |
| `total_reactions` | `int` | raw count of all reactors (normal + super); kept for range queries |
| `weighted_total` | `float` | weighted sum: normal = 1.0, super = 1.5 |
| `reply_created` | `bool` | true once a reply has been sent to an uneditable predecessor post |

key methods: `add_reaction`, `add_super_reaction`, `remove_reaction`, `remove_super_reaction`, `clear_emoji_reactions`, `clear_all_reactions`, `get_by_starboard_message`, `get_random`, `set_starboard_message`, `leaderboard_most_stars`, `leaderboard_most_starred`, `leaderboard_most_given`

---

## Sweeps

after each new starboard post is created, the bot checks if the same author has consecutive posts at the tail of the guild's starboard history and announces milestones:

| streak | announcement |
|---|---|
| 3 | `@user sweeps! 🧹` |
| 5 | `@user sweeps more! 🧹🥈` |
| 11 | `@user sweeps even more! 🧹🥇` |

only announces at exactly those counts - no announcement at 4, 6, etc. errors during sweep check are swallowed so they never block post creation.

---

## metadata

```yaml
last_updated: 6 May 2026
```
