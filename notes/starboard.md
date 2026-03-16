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
- a reaction on the response to a /star random or /star lost command should count towards the message it refers to.

---

## Post Format

### Content string

```
⭐ **4** | 🌟 **1** | https://discord.com/channels/<guild>/<channel>/<message>
```

- only emojis with at least one reaction are listed
- sorted by count descending
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

## Key Functions (`attubot/client/starboard.py`)

| Function | Purpose |
|---|---|
| `handle_star_add(guild_id, channel_id, message_id, user_id, emoji_str)` | entry point for `on_raw_reaction_add` |
| `handle_star_remove(guild_id, channel_id, message_id, user_id, emoji_str)` | entry point for `on_raw_reaction_remove` |
| `build_content(reactions, jump_url, emoji_colors)` | builds the content string |
| `dominant_color(reactions, emoji_colors)` | returns the color int for the highest-count emoji |
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
| `/fix starboard` | ingest existing starboard posts into the database |
| `/fix starboard-recount` | recount all reaction totals from stored reaction data |

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
| `reactions` | `dict[str, list[int]]` | emoji -> list of user ids who reacted |
| `total_reactions` | `int` | sum of all reaction counts (denormalized for queries) |

key methods: `add_reaction`, `remove_reaction`, `get_by_starboard_message`, `get_random`, `set_starboard_message`, `leaderboard_most_stars`, `leaderboard_most_starred`, `leaderboard_most_given`
