# Egg Game

Reference for the egg collection mini-game - behavior rules, storage schema, key functions, and commands.

---

## Overview

A seasonal event that activates automatically on hatch day each year. While active, players can run `/egg` to collect eggs that hatch into random creatures over time. The event's slash commands are in `attubot/commands/eggs.py` and loaded at startup via the normal extension discovery; `setup()` guards registration to only occur on or after hatch day. `HatchTask` handles the mid-run case where the bot started before hatch day and needs to reload the extension when the day arrives.

---

## Behavior Rules

1. `/egg` has a 15-minute cooldown per user per guild. The cooldown timestamp is stored in MongoDB and survives bot restarts.
2. Each `/egg` call rolls a rarity: common 55%, uncommon 25%, rare 13%, legendary 5%, mythical 2%.
3. The egg is posted as a rarity-specific custom emoji in the user's personal thread inside `#eggs`. One thread per user per guild, created on first collection and reused thereafter.
4. Hatch durations: common 30m, uncommon 2h, rare 8h, legendary 24h, mythical 48h.
5. `/eggs hatch` finds the oldest ready egg (hatches_at <= now). If none is ready, it shows a relative timestamp for the next one. If no eggs exist at all, it says so.
6. The egg is marked hatched in MongoDB **before** the animation starts. A restart during the animation will not double-hatch the egg.
7. Animation sequence: egg emoji sits unchanged for 10-15s → edit to 💢 → 1s pause → edit to result creature emoji.
8. The `#eggs` channel is created automatically on the first hatch day task run each year. Channel ID is persisted in `channels.eggs`.
9. Custom egg emojis (one per rarity) must be generated once via `/fix eggs generate`. They are stored in `BotTheme.egg_emojis` (MongoDB) and survive restarts.

---

## Hatch Day Detection

`hatch_date(year: int) -> date` in `attubot/eggs/hatching.py` computes the annual hatch day using the Meeus/Jones/Butcher algorithm (pure Python, no library). `HatchTask` runs hourly and checks `today >= hatch_date(today.year)` - eggs are active from hatch day onward through the rest of the year.

Known hatch days: 2024 = March 31, 2025 = April 20, 2026 = April 5.

---

## Storage

### `EggDocument` (collection: `eggs`)

| Field | Type | Purpose |
|---|---|---|
| `egg_id` | `str` | uuid4, unique |
| `guild_id` | `int` | guild |
| `user_id` | `int` | collector |
| `rarity` | `str` | `common` / `uncommon` / `rare` / `legendary` / `mythical` |
| `collected_at` | `float` | unix timestamp |
| `hatches_at` | `float` | `collected_at + hatch_durations[rarity]` |
| `hatched` | `bool` | marked true before animation starts |
| `result` | `str \| None` | unicode emoji char set at hatch time |
| `message_id` | `int \| None` | thread message ID for the animation |

Indexes: `(guild_id, user_id)`, `egg_id` unique.

### `EggUserDocument` (collection: `egg_users`)

| Field | Type | Purpose |
|---|---|---|
| `guild_id` | `int` | guild |
| `user_id` | `int` | player |
| `thread_id` | `int` | personal egg thread; 0 if not yet created |
| `last_collected_at` | `float` | unix timestamp; 0.0 on first use |

Index: `(guild_id, user_id)` unique.

---

## Bot Presence

`PresenceUpdateTask` (`attubot/tasks/presence.py`) sets the bot's presence to "Watching X eggs hatch" where X is the total hatched egg count. It runs on a 30-minute fallback schedule and is triggered immediately via `scheduler.add_job()` on two events:
- `HatchTask` fires it on hatch day start (or when the bot first detects it's on/after hatch day)
- `run_hatch_animation()` fires it after each egg finishes hatching

The task does nothing on non-hatch-day dates.

---

## Key Functions (`attubot/eggs/hatching.py`)

| Function | Purpose |
|---|---|
| `hatch_date(year)` | Meeus/Jones/Butcher algorithm; returns hatch day `date` for the given year |
| `ensure_eggs_ready()` | idempotent setup: creates `#eggs` channel + intro message if `channels.eggs == 0` |
| `get_or_create_user_thread(guild_id, user_id, username)` | fetches or creates the user's egg thread; handles cache miss and deleted threads |
| `collect_egg(guild_id, user_id, username)` | cooldown check, rarity roll, thread post, DB insert, cooldown update; raises `ValueError` on cooldown |
| `hatch_egg(guild_id, user_id)` | finds oldest ready egg, marks hatched, fires animation task; returns `(jump_url, None)` / `('', next_ts)` / `('no_eggs', None)` |
| `run_hatch_animation(message, result, rarity)` | three-stage edit sequence (egg → 💢 → result); triggers `PresenceUpdateTask` when done |

---

## Commands

Slash commands are defined in `attubot/commands/eggs.py`. The extension is auto-loaded at startup; `setup()` only registers the commands if `today >= hatch_date(today.year)`. If the bot starts before hatch day, `HatchTask` calls `bot.reload_extension()` when hatch day arrives.

| Command | Purpose |
|---|---|
| `/egg` | collect an egg (15m cooldown) |
| `/eggs hatch` | hatch the oldest ready egg |
| `/eggs view` | link to your egg collection thread |
| `/fix eggs generate` | upload custom egg emojis to secondary server and save IDs (owner only, run once) |
| `/debug eggs show <rarity>` | display the emoji and full hatch pool for a rarity (owner only) |
| `/debug eggs preview <rarity>` | run a full hatch animation in the current channel with no DB writes (owner only) |

---

## Setup

1. Run `/fix eggs generate` once in the secondary (emoji) server to create the five custom emojis and store their IDs.
2. The `#eggs` channel is created automatically when `HatchTask` detects hatch day. No manual setup required.
3. `/eggs hatch`, `/egg`, and `/eggs view` are only registered while the extension is loaded (hatch day onward for the season). Use `/debug eggs preview` to test the animation any time.
