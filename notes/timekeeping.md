# Timekeeping System

AttuBot tracks an in-universe calendar by computing the current year from a configurable real-world epoch. This note describes the system in enough detail to understand the math, debug issues, and work on the relevant code.

---

## Core Concepts

| Term | Description |
|---|---|
| **epoch** | the real-world timestamp at which a specific in-universe year began |
| **epoch year** | the in-universe year number that the epoch timestamp corresponds to |
| **year length** | how many real-world days make up one in-universe year |
| **rollover time** | the time of day (guild-local) at which a year transitions |
| **rollover minutes** | stored in MongoDB as minutes since midnight; the legacy string format (`"17:00"`) is handled by a model validator in `GuildEpoch` |
| **marker** | a Discord message snowflake recorded when a year transition is announced; used to link to the start of a year in lore channels |

All epoch values are stored as Unix timestamps (seconds). Year numbers are always positive integers.

---

## Year Calculation

Given an epoch timestamp, epoch year, and year length, the current in-universe year is computed daily:

```
elapsed_days = (today_at_rollover - epoch_at_rollover).total_seconds() / 86400

current_year = epoch_year + (elapsed_days // year_length)

# edge case: if today is exactly a rollover boundary, and the rollover hasn't happened yet,
# we are still in the previous year
if (elapsed_days % year_length) == 0 and now < today_at_rollover:
    current_year -= 1
```

See `get_year_status()` in `attubot/calendar.py` for the live implementation.

---

## Year Spans

A `AttuYearSpan` holds the start and end Unix timestamps for a given year and its duration in days.

- **past years** - loaded from the `Year` database record (fast path), or reconstructed from marker snowflakes (fallback)
- **current year** - start from the `Year` record or marker; end computed as the next rollover datetime
- **next year** - start is the next rollover; end is one year length after that
- **future years** - both start and end are projected forward from the next rollover

See `get_year_span()` in `attubot/calendar.py`.

---

## Rollover Check

`NovaYearTask` (`attubot/tasks/nova_year.py`) runs on a schedule and checks whether the current year has advanced. When it detects a transition:

1. the outgoing year's `Year` record is closed with its end timestamp
2. a new `Year` record is created for the incoming year
3. year link posts in configured channels are refreshed
4. an announcement is sent to the configured announcements channel

---

## Pausing and Dilation

- **pause** (`/time pause`) - sets `epoch.paused = true`; rollover checks are skipped; `get_next_year()` returns epoch 0
- **resume** (`/time resume`) / **dilate** (`/time dilate <days>`) - calls `move_epoch()` in `calendar.py`, which recalculates the epoch so the new year length takes effect without disrupting the current year (see inline comments in `move_epoch()` for the three-case logic)

---

## Manual Advance

`/time advance` forces the year forward immediately, bypassing the schedule. It calls the same rollover job that `NovaYearTask` would call.

---

## Code References

| File | Role |
|---|---|
| `attubot/calendar.py` | `get_year_status()`, `get_next_year()`, `get_year_span()`, `move_epoch()` |
| `attubot/tasks/nova_year.py` | scheduled rollover check and `job_construct_year_links()` |
| `attubot/markers.py` | `YearMarker` - associates a Discord snowflake with a year and channel |
| `attubot/years.py` | `Year` - database-backed record of each completed or active year |
| `attubot/commands/time.py` | `/time advance`, `/time pause`, `/time resume`, `/time dilate` |
| `attubot/commands/year.py` | `/year check`, `/year link`, `/year search` |
| `attubot/config.py` | `GuildEpoch` - Pydantic model that holds and validates epoch config |
