# Egg Game

Reference for the egg collection mini-game - behavior rules, storage schema, key functions, and commands.

---

## Overview

An egg collection mini-game. Players can run `/egg` to collect eggs that hatch into random creatures over time. Slash commands are in `apps/bot/nova_core/commands/eggs.py`.

---

## Behavior Rules

1. `/egg` has a 10-minute cooldown per user per guild. The cooldown timestamp is stored in MongoDB and survives bot restarts.
2. Each `/egg` call rolls a rarity: common 55%, uncommon 25%, rare 13%, legendary 5%, mythical 2%.
3. The egg is posted as a rarity-specific custom emoji in the user's personal thread inside `#eggs`. One thread per user per guild, created on first collection and reused thereafter.
4. Hatch durations: common 30m, uncommon 2h, rare 8h, legendary 24h, mythical 48h.
5. `/eggs hatch` finds the oldest ready egg (hatches_at <= now). If none is ready, it shows a relative timestamp for the next one. If no eggs exist at all, it says so.
6. The egg is marked hatched in MongoDB **before** the animation starts. A restart during the animation will not double-hatch the egg.
7. Animation sequence: egg emoji sits unchanged for 10-15s → edit to 💢 → 1s pause → edit to result creature emoji.
8. The `#eggs` channel is created automatically on first use via `ensure_eggs_ready()`. Channel ID is persisted in `channels.eggs`.
9. Custom egg emojis (one per rarity) must be generated once via `/fix eggs generate`. They are stored in `BotTheme.egg_emojis` (MongoDB) and survive restarts.

---

## Hatch Day

`hatch_date(year: int) -> date` in `apps/bot/nova_core/eggs/hatching.py` computes the annual hatch day using the Meeus/Jones/Butcher algorithm (pure Python, no library).

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

`PresenceUpdateTask` (`apps/bot/nova_core/tasks/presence.py`) sets the bot's presence to "Watching X eggs hatch" where X is the total hatched egg count. It runs on a 30-minute fallback schedule and is triggered immediately via `scheduler.add_job()` after each egg finishes hatching (`run_hatch_animation()`).

The task does nothing on non-hatch-day dates.

---

## Key Functions (`apps/bot/nova_core/eggs/hatching.py`)

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

Slash commands are defined in `apps/bot/nova_core/commands/eggs.py`.

| Command | Purpose |
|---|---|
| `/egg` | collect an egg (15m cooldown) |
| `/eggs hatch` | hatch the oldest ready egg |
| `/eggs view` | link to your egg collection thread |
| `/eggs give @user [rarity]` | give one of your eggs to another user |
| `/eggs progress` | show per-rarity and total unique creature progress with progress bars |
| `/fix eggs generate` | upload custom egg emojis to secondary server and save IDs (owner only, run once) |
| `/fix emoji progress` | upload progress bar emojis to secondary server and save IDs (owner only, run once) |
| `/debug eggs show <rarity>` | display the emoji and full hatch pool for a rarity (owner only) |
| `/debug eggs preview <rarity>` | run a full hatch animation in the current channel with no DB writes (owner only) |

---

## Egg Gifting

`/eggs give @user [rarity]` lets any player transfer one of their eggs (hatched or unhatched) to another guild member. Unhatched eggs keep their original `hatches_at` timer after transfer.

**Selection logic:**
- If `rarity` is `common`/`uncommon`/`rare`/`legendary`/`mythical`: picks the giver's oldest unhatched egg of that rarity and goes straight to an offer.
- If `rarity` is `hatched` or omitted: shows a Discord select menu with deduplicated options (one entry per distinct rarity for unhatched eggs, one entry per distinct creature emoji for hatched ones). Selecting an entry picks the oldest matching egg.

**Offer flow:**
1. A public message is posted in the current channel: "{giver} wants to give {recipient} a [emoji]. accept?" with a jump link to the egg in the giver's thread.
2. The recipient has two buttons: **Accept** and **Decline** (only they can click). The offer expires after 60 minutes.
3. On **Accept**: the original thread message is deleted from the giver's thread, the egg (or creature) is reposted in the recipient's thread (created if they don't have one), and the DB is updated with the new `user_id` and `message_id`.
4. On **Decline** or timeout: the offer message is edited to say so; no DB changes occur.

**Key functions (`apps/bot/nova_core/eggs/hatching.py`):**

| Function | Purpose |
|---|---|
| `transfer_egg(guild_id, egg_id, from_user_id, to_user_id, to_username)` | core transfer: delete old message, repost in recipient thread, update DB |

**Key views (`apps/bot/nova_core/commands/eggs.py`):**

| Class | Purpose |
|---|---|
| `EggGiftOfferView` | public offer message with Accept/Decline buttons; 5-min timeout |
| `EggSelectView` / `_EggSelectMenu` | ephemeral select menu showing deduplicated egg options |

**New `EggRepository` methods (`packages/shared-models/attu_models/repositories.py`):**

| Method | Purpose |
|---|---|
| `transfer(egg_id, new_user_id, new_message_id)` | update ownership and thread message id |
| `get_oldest_unhatched_by_rarity(guild_id, user_id, rarity)` | oldest unhatched egg of a specific rarity |
| `get_oldest_hatched_by_result(guild_id, user_id, result)` | oldest hatched egg with a specific creature emoji |
| `list_unhatched(guild_id, user_id)` | all unhatched eggs sorted by `hatches_at` asc |
| `list_hatched(guild_id, user_id)` | all hatched eggs sorted by `collected_at` asc |

---

## Egg Progress

`/eggs progress` shows a Pokédex-style completion tracker: how many distinct creatures you've hatched out of each rarity's full pool. Output is one line per rarity plus a totals line, each with a 10-segment progress bar and `n/pool_size` count. The last line shows raw totals: `X eggs collected; Y eggs hatched`. the embed title is set to `"{display_name}'s egg collection"`.

Pool sizes: common 27, uncommon 23, rare 20, legendary 12, mythical 3, total 85.

**Progress bar rendering (`apps/bot/nova_core/eggs/emojis.py`):**

| Function | Purpose |
|---|---|
| `ensure_progress_emojis(guild)` | upload 6 PNG segments from `assets/emoji/7783-progress-bar-emojigg-pack/` to a guild; create only missing ones |
| `render_progress_bar(filled, total, segments=10)` | build a bar string from `progress_emojis` IDs; falls back to unicode blocks if not configured |

Segment keys in `BotTheme.progress_emojis`: `left_full`, `left_empty`, `none_full`, `none_empty`, `right_full`, `right_empty`. Discord emoji names: `progress_{key}`.

**`EggRepository` method (`packages/shared-models/attu_models/repositories.py`):**

| Method | Purpose |
|---|---|
| `get_user_egg_stats(guild_id, user_id)` | single query returning `(total_collected, total_hatched, unique_per_rarity)` |

---

## Setup

1. Run `/fix eggs generate` once in the secondary (emoji) server to create the five custom emojis and store their IDs.
2. Run `/fix emoji progress` once in the secondary (emoji) server to upload the six progress bar segment emojis and store their IDs.
3. The `#eggs` channel is created automatically on first use via `ensure_eggs_ready()`. No manual setup required.
4. Use `/debug eggs preview` to test the animation any time.

---

## metadata

```yaml
last_updated: 2026-08-22
```
