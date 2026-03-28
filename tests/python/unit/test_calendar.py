"""
AttuBot - Calendar System Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Baseline tests for the epoch/calendar system. These verify the existing behavior
of get_year_status(), get_next_year(), and related functions so that refactoring
can be checked for regressions.

All tests use freeze_time to pin wall-clock time for deterministic results.
The test guild epoch starts at 2024-01-01 00:00:00 utc with:
  - year = 1, length = 14 days, rollover at 17:00 utc
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun import freeze_time

from attubot.client.calendar import AttuYearSpan, format_year_line, get_next_year, get_year_status, haracalnde_date
from attubot.config import GuildEpoch
from tests.conftest import test_guild


utc = ZoneInfo('UTC')


# --- GuildEpoch.get_rollover_time() ---


class TestGetRolloverTime:
    def test_default_rollover(self, guild):
        """Default 1020 minutes = 17:00"""
        result = guild.epoch.get_rollover_time()
        assert result.hour == 17
        assert result.minute == 0
        assert result.tzinfo is not None

    def test_midnight_rollover(self, make_guild):
        cfg = make_guild(rollover_minutes=0)
        result = cfg.epoch.get_rollover_time()
        assert result.hour == 0
        assert result.minute == 0

    def test_noon_rollover(self, make_guild):
        cfg = make_guild(rollover_minutes=720)
        result = cfg.epoch.get_rollover_time()
        assert result.hour == 12
        assert result.minute == 0

    def test_end_of_day_rollover(self, make_guild):
        cfg = make_guild(rollover_minutes=1439)
        result = cfg.epoch.get_rollover_time()
        assert result.hour == 23
        assert result.minute == 59


# --- GuildEpoch legacy validator ---


class TestEpochValidator:
    def test_legacy_rollover_time_string(self):
        """Old rollover_time string format should be converted to rollover_minutes"""
        epoch = GuildEpoch.model_validate({'time': 0, 'year': 1, 'length': 14, 'paused': False, 'rollover_time': '17:00'})
        assert epoch.rollover_minutes == 1020

    def test_legacy_rollover_time_noon(self):
        epoch = GuildEpoch.model_validate({'time': 0, 'year': 1, 'length': 14, 'paused': False, 'rollover_time': '12:30'})
        assert epoch.rollover_minutes == 750

    def test_default_rollover_when_missing(self):
        epoch = GuildEpoch(time=0, year=1, length=14, paused=False)
        assert epoch.rollover_minutes == 1020


# --- get_year_status() ---


class TestGetYearStatus:
    @freeze_time('2024-01-08 12:00:00')
    def test_mid_year(self, guild):
        """7 days into a 14-day year, before rollover → year 1"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 7
        assert year == 1

    @freeze_time('2024-01-02 12:00:00')
    def test_day_one(self, guild):
        """1 day after epoch start → year 1"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 1
        assert year == 1

    @freeze_time('2024-01-15 18:00:00')
    def test_boundary_after_rollover(self, guild):
        """Exactly 14 days, after rollover → year 2"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 14
        assert year == 2

    @freeze_time('2024-01-15 12:00:00')
    def test_boundary_before_rollover(self, guild):
        """Exactly 14 days, before rollover → still year 1 (boundary correction)"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 14
        assert year == 1

    @freeze_time('2024-01-29 18:00:00')
    def test_multiple_years_elapsed(self, guild):
        """28 days = 2 full years → year 3"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 28
        assert year == 3

    @freeze_time('2024-02-26 18:00:00')
    def test_many_years(self, guild):
        """56 days = 4 full years → year 5"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 56
        assert year == 5

    @freeze_time('2024-01-01 12:00:00')
    def test_epoch_start_day_before_rollover(self, guild):
        """Day zero, before rollover → boundary correction, year 0"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 0
        # At boundary (0 % 14 == 0) and before rollover → year - 1 = 0
        assert year == 0

    @freeze_time('2024-01-01 18:00:00')
    def test_epoch_start_day_after_rollover(self, guild):
        """Day zero, after rollover → year 1"""
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 0
        assert year == 1

    @freeze_time('2024-01-08 12:00:00')
    def test_different_year_length(self, make_guild):
        """7-day years: 7 days in = boundary"""
        make_guild(length=7)
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 7
        # At boundary, before rollover → year correction
        assert year == 1

    @freeze_time('2024-01-08 18:00:00')
    def test_different_year_length_after_rollover(self, make_guild):
        """7-day years: 7 days in, after rollover = year 2"""
        make_guild(length=7)
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 7
        assert year == 2

    @freeze_time('2024-01-08 12:00:00')
    def test_uses_primary_guild_when_none(self, guild):
        """Passing guild=None uses primary guild"""
        elapsed, year = get_year_status(None)
        assert elapsed == 7
        assert year == 1

    @freeze_time('2024-01-08 12:00:00')
    def test_base_year_offset(self, make_guild):
        """epoch.year != 1 should offset the result"""
        make_guild(year=10)
        elapsed, year = get_year_status(test_guild)
        assert elapsed == 7
        assert year == 10


# --- get_next_year() ---


class TestGetNextYear:
    @freeze_time('2024-01-08 12:00:00')
    def test_mid_year(self, guild):
        """7 days in, 7 days until next year boundary"""
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 15, 17, 0, tzinfo=utc)
        assert result == expected

    @freeze_time('2024-01-15 18:00:00')
    def test_boundary_after_rollover(self, guild):
        """At boundary after rollover → next year is one full length away"""
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 29, 17, 0, tzinfo=utc)
        assert result == expected

    @freeze_time('2024-01-15 12:00:00')
    def test_boundary_before_rollover(self, guild):
        """At boundary before rollover → next year is today at rollover"""
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 15, 17, 0, tzinfo=utc)
        assert result == expected

    @freeze_time('2024-01-10 12:00:00')
    def test_near_end_of_year(self, guild):
        """9 days in → 5 days until boundary"""
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 15, 17, 0, tzinfo=utc)
        assert result == expected

    @freeze_time('2024-01-02 12:00:00')
    def test_start_of_year(self, guild):
        """1 day in → 13 days remaining"""
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 15, 17, 0, tzinfo=utc)
        assert result == expected

    def test_paused_returns_epoch_zero(self, make_guild):
        """When paused, returns unix epoch 0"""
        make_guild(paused=True)
        result = get_next_year(test_guild)
        assert result == datetime.fromtimestamp(0, tz=utc)

    @freeze_time('2024-01-08 12:00:00')
    def test_uses_primary_guild_when_none(self, guild):
        result = get_next_year(None)
        expected = datetime(2024, 1, 15, 17, 0, tzinfo=utc)
        assert result == expected

    @freeze_time('2024-01-04 12:00:00')
    def test_short_year_length(self, make_guild):
        """7-day years: 3 days in → 4 days remaining"""
        make_guild(length=7)
        result = get_next_year(test_guild)
        expected = datetime(2024, 1, 8, 17, 0, tzinfo=utc)
        assert result == expected


# --- format_year_line() ---


class TestFormatYearLine:
    def test_contains_year_number(self):
        result = format_year_line(1)
        assert 'Year 1 PC' in result

    def test_contains_heading(self):
        result = format_year_line(5, level=2)
        assert result.startswith('##')

    def test_different_years_get_different_separators(self):
        """Adjacent years should get different separator patterns"""
        r1 = format_year_line(1)
        r2 = format_year_line(2)
        assert r1 != r2

    def test_level_wraps(self):
        """Level wraps at 7"""
        r1 = format_year_line(1, level=1)
        r2 = format_year_line(1, level=8)
        assert r1 == r2

    def test_high_year_number(self):
        result = format_year_line(9999)
        assert 'Year 9999 PC' in result

    def test_year_zero(self):
        """Year 0 shouldn't crash"""
        result = format_year_line(0)
        assert 'Year 0 PC' in result


# --- haracalnde_date() ---
#
# Epoch: time=1704067200 (2024-01-01 00:00 utc), year=1, length=14, rollover=17:00 utc
# epoch_at_rollover = 1704128400 (Jan 1 2024 17:00 utc)
# year1_span: start=1704128400, end=1705338000 (Jan 15 17:00 utc)
# year2_span: start=1705338000, end=1706547600 (Jan 29 17:00 utc)


class TestHaracalndeDate:
    EPOCH_ROLLOVER = 1704128400
    YEAR1_SPAN = AttuYearSpan(start_time=1704128400, end_time=1705338000, duration=14)
    YEAR2_SPAN = AttuYearSpan(start_time=1705338000, end_time=1706547600, duration=14)

    @freeze_time('2024-01-08 12:00:00')
    @pytest.mark.asyncio
    async def test_paused(self, make_guild):
        """Paused calendar returns 'Paused at N PC' regardless of timestamp"""
        make_guild(paused=True)
        result = await haracalnde_date(1704736800, test_guild)
        assert result == 'Paused at 1 PC'

    @pytest.mark.asyncio
    async def test_epoch_start(self, guild):
        """Exact epoch rollover timestamp maps to 1-1 1 PC"""
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = self.YEAR1_SPAN
            result = await haracalnde_date(self.EPOCH_ROLLOVER, test_guild)
        assert result == '1-1 1 PC'

    @pytest.mark.asyncio
    async def test_mid_year(self, guild):
        """Jan 8 18:00 utc: 7d 1h into year 1 → proportional position in month 7"""
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = self.YEAR1_SPAN
            result = await haracalnde_date(1704736800, test_guild)
        assert result == '2-7 1 PC'

    @pytest.mark.asyncio
    async def test_year_boundary_after_rollover(self, guild):
        """Jan 15 18:00 utc: just past year 2 rollover → early month 1 of year 2"""
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = self.YEAR2_SPAN
            result = await haracalnde_date(1705341600, test_guild)
        assert result == '2-1 2 PC'

    @pytest.mark.asyncio
    async def test_year_boundary_before_rollover(self, guild):
        """Jan 15 12:00 utc: boundary correction → still year 1, near end"""
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = self.YEAR1_SPAN
            result = await haracalnde_date(1705320000, test_guild)
        assert result == '25-12 1 PC'

    @pytest.mark.asyncio
    async def test_tt_before_epoch_rollover(self, guild):
        """Jan 1 12:00 utc: before epoch rollover → boundary correction → 1 TT"""
        result = await haracalnde_date(1704110400, test_guild)
        assert result == '5-12 1 TT'

    @pytest.mark.asyncio
    async def test_tt_one_year_before_epoch(self, guild):
        """Dec 18 2023 18:00 utc: 14 days before epoch, after rollover → 1-1 1 TT"""
        result = await haracalnde_date(1702922400, test_guild)
        assert result == '1-1 1 TT'

    @pytest.mark.asyncio
    async def test_tt_two_years_before_epoch(self, guild):
        """Dec 4 2023 18:00 utc: 28 days before epoch, after rollover → 1-1 2 TT"""
        result = await haracalnde_date(1701712800, test_guild)
        assert result == '1-1 2 TT'

    @pytest.mark.asyncio
    async def test_uses_year_span_not_epoch_length(self, guild):
        """When year_span covers 30 real-world days, position scales to that length"""
        span_30d = AttuYearSpan(start_time=1704128400, end_time=1706720400, duration=30)
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = span_30d
            # Jan 8 17:00 utc: exactly 7 days after epoch rollover
            result = await haracalnde_date(1704733200, test_guild)
        # 604800s / 2592000s * 360 = 84 → month 3, day 25
        assert result == '25-3 1 PC'

    @pytest.mark.asyncio
    async def test_no_db_record_fallback(self, guild):
        """When year_span has no data, fall back to epoch.length scaling"""
        empty_span = AttuYearSpan(start_time=0, end_time=0, duration=0)
        with patch('attubot.client.calendar.get_year_span', new_callable=AsyncMock) as mock_span:
            mock_span.return_value = empty_span
            # Jan 8 18:00 utc: day_of_year=7, int(7*360/14)=180 → 1-7
            result = await haracalnde_date(1704736800, test_guild)
        assert result == '1-7 1 PC'
