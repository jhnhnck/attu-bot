"""
AttuBot - Calendar Utils
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import date, datetime, timedelta

from pydantic import BaseModel

from attubot.config import GuildEpoch, NovaConfig
from attubot.logging import get_logger

# --- Initialization ---

logger = get_logger(__name__)

# --- Components ---

class AttuYearSpan(BaseModel):
    start_time: int
    end_time: int
    duration: int

# --- Utilities ---

def format_year_line(year) -> str:
    separators = ['<', '=', '+', r'\>', '/', '&', ':', '$', r'\*', '%', '@', '⁂', 'xXx', '\\\\', '?', '^', r'\|', r'\~', '-']
    flipped_separators = {'<': '>', r'\>': '<', '/': '\\\\', '\\\\': '/'}
    sep = separators[year % len(separators)]

    if len(sep) > 2:
        return f'# {sep} Year {year} PC {sep}'
    if sep in flipped_separators:
        return f'# {sep * 3} Year {year} PC {flipped_separators[sep] * 3}'
    else:
        return f'# {sep * 3} Year {year} PC {sep * 3}'


def get_year_status(guild: int | None = None) -> tuple[int, int]:
    epoch: GuildEpoch = (NovaConfig.primary() if guild is None else NovaConfig.guild(guild)).epoch

    today = datetime.combine(date.today(), epoch.rollover_time)
    epoch_time = datetime.combine(datetime.fromtimestamp(epoch.time).astimezone(), epoch.rollover_time)
    time_diff_sec = (today - epoch_time).total_seconds()

    elapsed_days = int(time_diff_sec / 86400)
    year = epoch.year + (elapsed_days // epoch.length)

    if (elapsed_days % epoch.length) == 0 and datetime.now().time() < epoch.rollover_time:
        year -= 1

    return elapsed_days, year


def get_next_year(guild: int | None = None) -> datetime:
    epoch: GuildEpoch = (NovaConfig.primary() if guild is None else NovaConfig.guild(guild)).epoch

    if epoch.paused:
        return datetime.fromtimestamp(0).astimezone()

    elapsed_days, _ = get_year_status(guild)
    new_date = datetime.combine(date.today(), epoch.rollover_time) + timedelta((epoch.length - elapsed_days) % epoch.length)

    if (elapsed_days % epoch.length) == 0 and datetime.now().time() >= epoch.rollover_time:
        new_date += timedelta(days=epoch.length)

    return new_date


async def get_year_span(year: int, guild: int | None = None) -> AttuYearSpan:
    from attubot.markers import YearMarker  # noqa: PLC0415

    epoch: GuildEpoch = (NovaConfig.primary() if guild is None else NovaConfig.guild(guild)).epoch
    result = AttuYearSpan(start_time=0, end_time=0, duration=0)

    _, current_year = get_year_status()
    next_year = get_next_year()

    # Invalid Years
    if year <= 0 or year > 10000:
        logger.error(f'get_year() requested with invalid year: {year}')
        year = 10000 if year > 0 else 1

    # Past Years
    elif year < current_year:
        result.start_time = await YearMarker.timestamp(year)
        result.end_time = await YearMarker.timestamp(year + 1)

    # Current Year
    elif year == current_year:
        result.start_time = await YearMarker.timestamp(year)
        result.end_time = int(next_year.timestamp())

    # Next Year
    elif year == (current_year + 1):
        result.start_time = int(next_year.timestamp())
        result.end_time = int((next_year + timedelta(days=(epoch.length * (year - current_year)))).timestamp()) if not epoch.paused else 0

    # Future Years
    elif not epoch.paused:
        result.start_time = int((next_year + timedelta(days=(epoch.length * (year - current_year - 1)))).timestamp())
        result.end_time = int((next_year + timedelta(days=(epoch.length * (year - current_year)))).timestamp())

    result.duration = round((result.end_time - result.start_time) / 86400)
    return result


# TODO: Shouldn't this be on the guild object
async def move_epoch(length: int, guild: int | None = None):
    elapsed_days, current_year = get_year_status()
    year_span = await get_year_span(current_year)
    cfg = NovaConfig.primary() if guild is None else NovaConfig.guild(guild)

    # handle picking new year time if paused
    if cfg.epoch.paused:
        friday = date.today() + timedelta(days=(11 - date.today().weekday()) % 7)

        # check if already passed trigger time
        if date.today().weekday() == 4 and datetime.now().time() >= cfg.epoch.rollover_time:
            friday += timedelta(days=7)

        await cfg.set_epoch(datetime.combine(friday, cfg.epoch.rollover_time), current_year + 1)

    # new length longer than current year has lasted, just extend
    elif length >= (elapsed_days % cfg.epoch.length):
        await cfg.set_epoch(datetime.combine(datetime.fromtimestamp(year_span.start_time).astimezone(), cfg.epoch.rollover_time).timestamp(), current_year)

    # wait for current year to complete first
    else:
        await cfg.set_epoch(year_span.end_time, current_year + 1)

    await cfg.set_year_length(length)
    logger.info(f'[{cfg!s}] New Epoch Set: {cfg.epoch.year} PC at <t:{cfg.epoch.time}:f> with year length of {cfg.epoch.length}')
