# Year Markers

Reference for the marker system - how markers are resolved, stored, and linked.

---

## Intent

A marker is the "header" message for a given year in a given channel. It lets `/year link` jump directly to the start of a year in any lore or canon channel.

The system is backed by the existing `messages` collection (see `apps/bot/doom_bot/client/messages.py`). There is no separate runtime marker table; the `year_markers` collection only stores admin overrides.

---

## What a Marker Is

The canonical marker for `(guild, channel, year)` is the message id of:

1. **Bot rollover header** - a message sent by the bot matching `format_year_line(year)` - e.g. `# <<< Year 5 PC <<<`
2. **Author header** - a message sent by an authorized marker author (`guild_config.users.markers`) containing a recognizable year header (repeated character, year number, optional "Year" / "PC")
3. **First message** - chronologically the first message in the channel during that year's time window
4. **Primary-channel fallback** - the marker from the first lore channel, used when the channel has no messages at all for the year

The `exact` flag is `True` for sources 1 and 2, `False` for sources 3 and 4.

---

## Resolver

`apps/bot/doom_bot/client/markers.py` exports `resolve_marker(guild, channel, year) -> ResolvedMarker`.

```python
@dataclass
class ResolvedMarker:
    guild: int
    channel: int
    year: int
    message: int  # message snowflake; 0 if not found
    exact: bool  # true if bot or author header
    source: str  # 'bot' | 'author' | 'first' | 'primary' | 'override' | 'none'
```

resolution order:

1. check `year_markers` collection for an admin override - if present, return it with `exact=True` and `source='override'`
2. query `messages` for a bot-authored message matching `format_year_line(year)` in the year window - `source='bot'`
3. query `messages` for a marker-author message matching `has_year_marker(year, content)` in the year window - `source='author'`
4. query `messages` for the first message (oldest `created_at`) in the year window - `source='first'`
5. if channel has no messages, resolve the primary lore channel's marker and return `source='primary'`
6. if nothing found, return `message=0, exact=False, source='none'`

the year window for a past year is `[year_record.start_time, year_record.end_time)`. for the current year, the window is `[year_record.start_time, now)`.

---

## Admin Override Storage

Admin overrides are stored in `year_markers` as before but are now the only thing written there. The collection schema stays:

```
{ guild, channel, message, year, exact: True, wiki_page: bool }
```

overrides are set via:
- `/marker save` - sets a specific message as exact marker for a channel+year
- `/marker set` - moves the guild-level timestamp reference
- web UI create/edit

`exact` is always `True` for overrides; the resolver never stores non-override markers.

---

## Year Formatted String - Removed

`YearDocument.formatted` is dropped. call `format_year_line(year)` directly wherever the heading text is needed.

---

## `/year link` Command Flow

command stays in `apps/bot/doom_bot/commands/year.py`. The search logic is in `apps/bot/doom_bot/client/markers.py`.

```
/year link <year> [channel]
   -> resolve_marker(guild, channel, year)
   -> format_message_link(guild, channel, marker.message, relative=(not marker.exact))
```

`format_message_link` with `relative=True` generates a `?` link (no exact anchor), `relative=False` generates a direct jump link.

---

## Year Link Construction

`job_construct_year_links` iterates lore channels, calls `resolve_marker` for each, and builds jump links. same as before but no Discord history queries.

---

## Web Markers API

Marker identity in the API uses `(year, channel)` - not year alone.

| Endpoint | Change |
|---|---|
| `GET /api/guilds/<id>/markers` | returns all override markers (across all channels) per guild |
| `GET /api/guilds/<id>/markers/<year>` | **removed** - use `?channel=<id>` on the list endpoint |
| `GET /api/guilds/<id>/markers/<year>/<channel>` | get specific override for year+channel |
| `POST /api/guilds/<id>/markers/<year>/<channel>` | upsert override |
| `DELETE /api/guilds/<id>/markers/<year>/<channel>` | delete override |
| `GET /api/guilds/<id>/markers/<year>/timestamp` | unchanged - returns timestamp for any marker |

---

## Repository Helpers (messages collection)

`MessageRepository` gets these new query methods used by the resolver:

| Method | Purpose |
|---|---|
| `find_bot_header(guild_id, channel_id, content_prefix, after, before)` | oldest bot message starting with given text in window |
| `find_author_message(guild_id, channel_id, author_ids, after, before)` | oldest message by any author_id in window |
| `find_first_message(guild_id, channel_id, after, before)` | oldest message in window |

window boundaries are unix timestamps (int). `before` is exclusive.

---

## Migrations

| Version | Change |
|---|---|
| 2.5.0 | remove `formatted` field from all `Year` documents; unset in existing docs |
| 2.5.1 | copy all existing `year_markers` docs that are not overrides into an archive collection; mark them read-only |
| 2.5.2 | drop `year_markers` runtime dependency; resolver only reads overrides |

---

## Key Functions (`apps/bot/doom_bot/client/markers.py`)

| Name | Purpose |
|---|---|
| `resolve_marker(guild, channel, year)` | main entry point; returns `ResolvedMarker` |
| `has_year_marker(year, content)` | checks if message content looks like a year header |
| `YearMarker.get(channel, year)` | get stored override, or None |
| `YearMarker.get_any(guild, year)` | get any override for a guild+year |
| `YearMarker.mark(year, message_id, channel, guild)` | store bot rollover marker as override |
| `YearMarker.all_for_guild(guild)` | list all overrides for a guild |
| `YearMarker.timestamp(year, guild)` | return unix timestamp from override snowflake |

---

## Commands

| Command | Purpose |
|---|---|
| `/year link <year> [channel]` | links to the year marker in a lore channel |
| `/year check <year>` | shows year span info |
| `/year search <year>` | generates discord search query |
| `/marker save <year> <link>` | override the marker for a channel+year with an exact link |
| `/marker set <year> <snowflake>` | move the guild-level start timestamp for a year |
| `/marker clear <year> <channel>` | delete the override for a channel+year |

---

## metadata

```yaml
last_updated: 6 May 2026
```
