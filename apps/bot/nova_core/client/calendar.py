# SPDX-License-Identifier: Apache-2.0
"""nova_core.client.calendar | calendar utils."""

from datetime import date, datetime, timedelta

import structlog
from pydantic import BaseModel

from nova_core.client.core import config
from nova_core.config import GuildEpoch


# --- Initialization ---

logger = structlog.stdlib.get_logger(__name__)
seconds_per_day = 86400

# --- Components ---


class AttuYearSpan(BaseModel):
    start_time: int
    end_time: int
    duration: int


# --- Utilities ---


def format_year_line(year: int, level: int = 1) -> str:
    separators = ['<', '=', '+', r'\>', '/', '&', ':', '$', r'\*', '%', '@', '⁂', 'xXx', '\\\\', '?', '^', r'\|', r'\~', '-']
    flipped_separators = {'<': '>', r'\>': '<', '/': '\\\\', '\\\\': '/'}
    sep = separators[year % len(separators)]
    level = level % 7

    if len(sep) > 2:
        return f'{"#" * level} {sep} Year {year} PC {sep}'
    if sep in flipped_separators:
        return f'{"#" * level} {sep * 3} Year {year} PC {flipped_separators[sep] * 3}'
    else:
        return f'{"#" * level} {sep * 3} Year {year} PC {sep * 3}'


def get_year_status(guild: int | None = None) -> tuple[int, int]:
    epoch: GuildEpoch = (config.primary() if guild is None else config.guild(guild)).epoch

    today = datetime.combine(date.today(), epoch.get_rollover_time())
    epoch_time = datetime.combine(datetime.fromtimestamp(epoch.time).astimezone(), epoch.get_rollover_time())
    time_diff_sec = (today - epoch_time).total_seconds()

    elapsed_days = int(time_diff_sec / seconds_per_day)
    year = epoch.year + (elapsed_days // epoch.length)

    if (elapsed_days % epoch.length) == 0 and datetime.now().astimezone() < today:
        year -= 1

    return elapsed_days, year


def get_next_year(guild: int | None = None) -> datetime:
    epoch: GuildEpoch = (config.primary() if guild is None else config.guild(guild)).epoch

    if epoch.paused:
        return datetime.fromtimestamp(0).astimezone()

    elapsed_days, _ = get_year_status(guild)
    new_date = datetime.combine(date.today(), epoch.get_rollover_time()) + timedelta((epoch.length - elapsed_days) % epoch.length)

    if (elapsed_days % epoch.length) == 0 and datetime.now().astimezone() >= new_date:
        new_date += timedelta(days=epoch.length)

    return new_date


async def get_year_span(year: int, guild: int | None = None) -> AttuYearSpan:
    from nova_core.client.markers import YearMarker
    from nova_core.client.years import Year

    _primary = config.get_guild_by_role('primary')
    guild_id = (_primary.id if _primary is not None else 0) if guild is None else guild
    epoch: GuildEpoch = (config.primary() if guild is None else config.guild(guild)).epoch
    result = AttuYearSpan(start_time=0, end_time=0, duration=0)

    _, current_year = get_year_status(guild)
    next_year = get_next_year(guild)

    # Invalid Years
    if year <= 0 or year > 10000:
        logger.error(f'get_year() requested with invalid year: {year}')
        year = 10000 if year > 0 else 1

    # Past Years — DB-first fast path via Year records
    elif year < current_year:
        year_record = await Year.get(guild_id, year)
        if year_record and year_record.end_time > 0:
            return year_record.to_span()

        # Fallback to marker-based computation
        result.start_time = await YearMarker.timestamp(year, guild_id) or 0
        result.end_time = await YearMarker.timestamp(year + 1, guild_id) or 0

    # Current Year — Year record for start_time, epoch math for projected end
    elif year == current_year:
        year_record = await Year.get(guild_id, year)
        if year_record and year_record.start_time > 0:
            result.start_time = year_record.start_time
        else:
            result.start_time = await YearMarker.timestamp(year, guild_id) or 0
        result.end_time = int(next_year.timestamp())

    # Next Year
    elif year == (current_year + 1):
        result.start_time = int(next_year.timestamp())
        result.end_time = int((next_year + timedelta(days=(epoch.length * (year - current_year)))).timestamp()) if not epoch.paused else 0

    # Future Years
    elif not epoch.paused:
        result.start_time = int((next_year + timedelta(days=(epoch.length * (year - current_year - 1)))).timestamp())
        result.end_time = int((next_year + timedelta(days=(epoch.length * (year - current_year)))).timestamp())

    result.duration = round((result.end_time - result.start_time) / seconds_per_day)
    return result


async def haracalnde_date(timestamp: int, guild: int | None = None) -> str:
    """Convert a unix timestamp to a formatted Haracalnde date string.

    Returns strings like '15-3 5 PC' (day-month year ERA). Uses actual year spans
    from the database to handle historically variable year lengths. Returns
    'Paused at N PC' when the calendar is paused.
    """
    epoch: GuildEpoch = (config.primary() if guild is None else config.guild(guild)).epoch

    if epoch.paused:
        _, current_year = get_year_status(guild)
        return f'Paused at {current_year} PC'

    ts_dt = datetime.fromtimestamp(timestamp).astimezone()
    ts_at_rollover = datetime.combine(ts_dt.date(), epoch.get_rollover_time())
    epoch_time = datetime.combine(datetime.fromtimestamp(epoch.time).astimezone(), epoch.get_rollover_time())
    time_diff_sec = (ts_at_rollover - epoch_time).total_seconds()

    elapsed_days = int(time_diff_sec / seconds_per_day)
    year = epoch.year + (elapsed_days // epoch.length)

    if (elapsed_days % epoch.length) == 0 and ts_dt < ts_at_rollover:
        year -= 1
        day_of_year = epoch.length - 1
    else:
        day_of_year = elapsed_days % epoch.length

    if year >= 1:
        year_span = await get_year_span(year, guild)
        if year_span.start_time > 0 and year_span.end_time > 0:
            span_sec = year_span.end_time - year_span.start_time
            haracalnde_pos = int((timestamp - year_span.start_time) / span_sec * 360)
        else:
            # fallback: no db record; approximate with current epoch.length
            haracalnde_pos = int(day_of_year * 360 / epoch.length)
        era = f'{year} PC'
    else:
        # tt era: no db records before 1 pc; approximate with current epoch.length
        haracalnde_pos = int(day_of_year * 360 / epoch.length)
        era = f'{1 - year} TT'

    haracalnde_pos = max(0, min(359, haracalnde_pos))
    month = haracalnde_pos // 30 + 1
    day = haracalnde_pos % 30 + 1
    return f'{day}-{month} {era}'


# TODO: Shouldn't this be on the guild object
async def move_epoch(length: int, guild: int | None = None):
    from nova_core.client.years import Year

    elapsed_days, current_year = get_year_status(guild)
    year_span = await get_year_span(current_year, guild)
    cfg = config.primary() if guild is None else config.guild(guild)
    _primary = config.get_guild_by_role('primary')
    guild_id = (_primary.id if _primary is not None else 0) if guild is None else guild

    old_year_length = cfg.epoch.length
    note = ''

    # handle picking new year time if paused
    if cfg.epoch.paused:
        friday = date.today() + timedelta(days=(11 - date.today().weekday()) % 7)
        friday_rollover = datetime.combine(friday, cfg.epoch.get_rollover_time())

        # check if already passed trigger time
        if date.today().weekday() == 4 and datetime.now().astimezone() >= friday_rollover:
            friday += timedelta(days=7)

        new_epoch_time = datetime.combine(friday, cfg.epoch.get_rollover_time()).timestamp()
        await cfg.set_epoch(new_epoch_time, current_year + 1)
        note = f'Epoch resumed from pause: Year {current_year + 1} will start on <t:{int(new_epoch_time)}:F>, length {old_year_length}→{length} days'

    # new length longer than current year has lasted, just extend
    elif length >= (elapsed_days % cfg.epoch.length):
        new_epoch_time = datetime.combine(datetime.fromtimestamp(year_span.start_time).astimezone(), cfg.epoch.get_rollover_time()).timestamp()
        await cfg.set_epoch(new_epoch_time, current_year)
        note = f'Epoch extended: Year {current_year} extended from {old_year_length} to {length} days (elapsed: {elapsed_days % old_year_length})'

    # wait for current year to complete first
    else:
        await cfg.set_epoch(year_span.end_time, current_year + 1)
        note = f'Epoch shortened: Year {current_year} will complete at {old_year_length} days, Year {current_year + 1} will be {length} days'

    await cfg.set_year_length(length)
    logger.info(f'[{cfg!s}] New Epoch Set: {cfg.epoch.year} PC at <t:{cfg.epoch.time}:f> with year length of {cfg.epoch.length}')

    # Update the current Year record with epoch change note
    current_year_record = await Year.get(guild_id, current_year)
    if current_year_record:
        existing_notes = current_year_record.notes
        updated_notes = f'{existing_notes}\n{note}' if existing_notes else note
        await current_year_record.update(notes=updated_notes.strip())
        logger.info(f'[{cfg!s}] Updated Year {current_year} record: {note}')
