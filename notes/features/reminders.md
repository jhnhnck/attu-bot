# reminders

reference for the in-universe date reminder system - behavior rules, storage schema, key functions, and commands.

---

## overview

users can set reminders that fire when a specific haracalnde calendar date arrives. reminders are one-shot: once delivered, they are marked fired and never re-triggered. the system uses dynamic scheduling to sleep until the next reminder's real-world fire time, recomputing from the attu date on each cycle so dilation changes are automatically reflected.

---

## behavior rules

1. `/remind add` creates a one-shot reminder for a target haracalnde date (year required, month and day optional).
2. year-only reminders fire at the start of the target year (rollover time).
3. year+month reminders fire at the start of that month within the year (day defaults to 1).
4. year+month+day reminders fire at the interpolated position within the year span.
5. reminders cannot be set for past dates or while the guild's calendar is paused.
6. delivery: the bot mentions the user in the channel where `/remind add` was invoked. if the channel no longer exists, it falls back to the guild's `meta_chat` channel. if both fail, the reminder is still marked fired.
7. the delivery message includes a jump URL linking back to the original `/remind add` response.
8. there is no per-user limit on active reminders.

---

## fire time computation

the haracalnde date is the source of truth. the real-world fire timestamp is computed dynamically by `compute_fire_time()` in `apps/bot/doom_bot/tasks/reminder.py`:

1. call `get_year_span(attu_year, guild_id)` to get the target year's `(start_time, end_time)`.
2. if year-only: fire at `start_time`.
3. otherwise: `haracalnde_pos = (month - 1) * 30 + (day - 1)` and `fire_ts = start_time + (haracalnde_pos / 360) * (end_time - start_time)`.

because `get_year_span()` uses the current epoch config, dilation changes via `/time dilate` are automatically reflected without any stored timestamps going stale. the task recomputes all fire times on every `next_run()` cycle.

---

## storage

collection: `reminders`

| field | type | description |
|---|---|---|
| `reminder_id` | `str` | uuid4, unique primary key |
| `guild_id` | `int` | guild where the reminder was created |
| `user_id` | `int` | user to notify |
| `channel_id` | `int` | channel where `/remind add` was used (delivery target) |
| `message_id` | `int` | bot response message id (for jump URL) |
| `attu_year` | `int` | target haracalnde year (PC era, >= 1) |
| `attu_month` | `int \| None` | target month (1-12) |
| `attu_day` | `int \| None` | target day (1-30) |
| `note` | `str` | optional user-provided note |
| `created_at` | `int` | unix timestamp of creation |
| `fired` | `bool` | true once delivered |
| `fired_at` | `int \| None` | unix timestamp when delivered |

indexes: unique on `reminder_id`; compound `(guild_id, fired, attu_year)` for task queries; compound `(guild_id, user_id, fired)` for user listing.

---

## commands

| command | description |
|---|---|
| `/remind add year month? day? note?` | create a reminder for a haracalnde date |
| `/remind list` | view your active reminders with approximate fire times |
| `/remind cancel reminder_id` | cancel a reminder by id (full uuid or 8-char prefix from `/remind list`) |

---

## key functions

| function | file | purpose |
|---|---|---|
| `compute_fire_time()` | `apps/bot/doom_bot/tasks/reminder.py` | convert a reminder's haracalnde date to a real-world datetime |
| `format_attu_date()` | `apps/bot/doom_bot/tasks/reminder.py` | format a reminder's target date as a readable string |
| `_deliver_reminder()` | `apps/bot/doom_bot/tasks/reminder.py` | send the notification message to the channel |
| `ReminderTask.next_run()` | `apps/bot/doom_bot/tasks/reminder.py` | compute the earliest fire time across all pending reminders |
| `ReminderTask.run()` | `apps/bot/doom_bot/tasks/reminder.py` | fire any overdue reminders |

---

## edge cases

- **calendar pause**: `/remind add` rejects when paused. the task skips paused-guild reminders. when resumed, next cycle picks them up.
- **dilation change**: fire times are recomputed from the haracalnde date each cycle, so no invalidation needed.
- **bot restart**: overdue reminders (fire time in the past) are delivered immediately on the next `run()`.
- **channel deleted**: falls back to `meta_chat` from the guild config.
- **guild removed**: `config.guild()` raises `UnauthorizedGuild`; reminder becomes dormant until the guild is re-added.
- **new reminder while sleeping**: `/remind add` calls `reminder_task.request_wake()` after inserting, which interrupts the task's current sleep so `next_run()` is re-evaluated immediately. this prevents a newly created reminder from being delayed until a prior sleep target expires.

---

## code references

| file | role |
|---|---|
| `apps/bot/doom_bot/tasks/reminder.py` | `ReminderTask`, `compute_fire_time()`, `_deliver_reminder()`, `format_attu_date()` |
| `apps/bot/doom_bot/commands/remind.py` | `/remind add`, `/remind list`, `/remind cancel` slash commands |
| `packages/shared-models/attu_models/documents.py` | `ReminderDocument` pydantic model (re-exported via `doom_bot.database.models`) |
| `packages/shared-models/attu_models/repositories.py` | `ReminderRepository` — CRUD + queries (re-exported via `doom_bot.database.repositories`) |

---

## metadata

```yaml
last_updated: 6 May 2026
```
