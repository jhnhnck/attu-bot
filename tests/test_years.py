"""
AttuBot - Year Model Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests for the Year runtime model (years.py). The repository layer is mocked
so these tests verify model logic, navigation, lifecycle methods, and the
to_span() conversion without requiring a real MongoDB connection.
"""

import os
import time as _time

os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock

import pytest

from attubot.calendar import SECONDS_PER_DAY, AttuYearSpan
from attubot.years import Year
from tests.conftest import TEST_GUILD

# --- Year Model Construction ---


class TestYearModel:
    def test_basic_construction(self, make_year):
        y = make_year()
        assert y.guild == TEST_GUILD
        assert y.year == 1
        assert y.start_time == 1704067200
        assert y.end_time == 1705276800
        assert y.duration == 14

    def test_defaults(self):
        y = Year(guild=TEST_GUILD, year=1, start_time=1704067200)
        assert y.end_time == 0
        assert y.duration == 0
        assert y.formatted == ''

    def test_formatted_field(self, make_year):
        y = make_year(formatted='# <<< Year 1 PC >>>')
        assert y.formatted == '# <<< Year 1 PC >>>'


# --- to_span() ---


class TestToSpan:
    def test_returns_attu_year_span(self, make_year):
        y = make_year(start_time=100, end_time=200, duration=1)
        span = y.to_span()
        assert isinstance(span, AttuYearSpan)

    def test_span_values(self, make_year):
        y = make_year(start_time=1704067200, end_time=1705276800, duration=14)
        span = y.to_span()
        assert span.start_time == 1704067200
        assert span.end_time == 1705276800
        assert span.duration == 14

    def test_span_current_year_no_end(self, make_year):
        """Current year has end_time=0"""
        y = make_year(end_time=0, duration=0)
        span = y.to_span()
        assert span.end_time == 0
        assert span.duration == 0


# --- Navigation ---


class TestNavigation:
    @pytest.mark.asyncio
    async def test_prev_returns_previous_year(self, mock_year_repo, make_year_doc, make_year):
        mock_year_repo.get = AsyncMock(return_value=make_year_doc(year=2))
        y = make_year(year=3)
        prev = await y.prev()
        assert prev is not None
        assert prev.year == 2
        mock_year_repo.get.assert_called_once_with(TEST_GUILD, 2)

    @pytest.mark.asyncio
    async def test_prev_year_one_returns_none(self, mock_year_repo, make_year):
        y = make_year(year=1)
        prev = await y.prev()
        assert prev is None
        mock_year_repo.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_prev_not_found_returns_none(self, mock_year_repo, make_year):
        mock_year_repo.get = AsyncMock(return_value=None)
        y = make_year(year=5)
        prev = await y.prev()
        assert prev is None

    @pytest.mark.asyncio
    async def test_next_returns_next_year(self, mock_year_repo, make_year_doc, make_year):
        mock_year_repo.get = AsyncMock(return_value=make_year_doc(year=4))
        y = make_year(year=3)
        nxt = await y.next()
        assert nxt is not None
        assert nxt.year == 4
        mock_year_repo.get.assert_called_once_with(TEST_GUILD, 4)

    @pytest.mark.asyncio
    async def test_next_not_found_returns_none(self, mock_year_repo, make_year):
        mock_year_repo.get = AsyncMock(return_value=None)
        y = make_year(year=10)
        nxt = await y.next()
        assert nxt is None


# --- Persistence Methods ---


class TestPersistence:
    @pytest.mark.asyncio
    async def test_save_calls_upsert(self, mock_year_repo, make_year):
        y = make_year(year=5, start_time=100, end_time=200, duration=1, formatted='test')
        await y.save()
        mock_year_repo.upsert.assert_called_once_with(
            guild=TEST_GUILD,
            year=5,
            start_time=100,
            end_time=200,
            duration=1,
            formatted='test',
            notes='',
        )

    @pytest.mark.asyncio
    async def test_update_modifies_instance_and_persists(self, mock_year_repo, make_year):
        y = make_year(year=3, end_time=0, duration=0)
        await y.update(end_time=999, duration=10)
        assert y.end_time == 999
        assert y.duration == 10
        mock_year_repo.update.assert_called_once_with(TEST_GUILD, 3, end_time=999, duration=10)

    @pytest.mark.asyncio
    async def test_update_ignores_unknown_fields(self, mock_year_repo, make_year):
        y = make_year()
        await y.update(nonexistent_field=42)
        # nonexistent_field should not be set on the model
        assert not hasattr(y, 'nonexistent_field') or getattr(y, 'nonexistent_field', None) is None
        # but it still gets passed to the repo (repo can handle/ignore it)
        mock_year_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_calls_repo(self, mock_year_repo, make_year):
        y = make_year(year=7)
        await y.delete()
        mock_year_repo.delete.assert_called_once_with(TEST_GUILD, 7)


# --- Class Methods ---


class TestClassMethods:
    @pytest.mark.asyncio
    async def test_get_found(self, mock_year_repo, make_year_doc):
        mock_year_repo.get = AsyncMock(return_value=make_year_doc(year=3))
        result = await Year.get(TEST_GUILD, 3)
        assert result is not None
        assert result.year == 3
        assert isinstance(result, Year)

    @pytest.mark.asyncio
    async def test_get_not_found(self, mock_year_repo):
        mock_year_repo.get = AsyncMock(return_value=None)
        result = await Year.get(TEST_GUILD, 99)
        assert result is None

    @pytest.mark.asyncio
    async def test_total(self, mock_year_repo, guild):
        mock_year_repo.total = AsyncMock(return_value=42)
        result = await Year.total(TEST_GUILD)
        assert result == 42
        mock_year_repo.total.assert_called_once_with(TEST_GUILD)

    @pytest.mark.asyncio
    async def test_total_uses_primary_guild(self, mock_year_repo, guild):
        mock_year_repo.total = AsyncMock(return_value=5)
        result = await Year.total()
        assert result == 5
        mock_year_repo.total.assert_called_once_with(TEST_GUILD)

    @pytest.mark.asyncio
    async def test_exists_true(self, mock_year_repo):
        mock_year_repo.exists = AsyncMock(return_value=True)
        assert await Year.exists(TEST_GUILD, 1) is True

    @pytest.mark.asyncio
    async def test_exists_false(self, mock_year_repo):
        mock_year_repo.exists = AsyncMock(return_value=False)
        assert await Year.exists(TEST_GUILD, 99) is False

    @pytest.mark.asyncio
    async def test_all_for_guild(self, mock_year_repo, make_year_doc):
        mock_year_repo.all_for_guild = AsyncMock(
            return_value=[
                make_year_doc(year=1),
                make_year_doc(year=2),
                make_year_doc(year=3),
            ]
        )
        results = await Year.all_for_guild(TEST_GUILD)
        assert len(results) == 3
        assert all(isinstance(r, Year) for r in results)
        assert [r.year for r in results] == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_all_for_guild_empty(self, mock_year_repo):
        mock_year_repo.all_for_guild = AsyncMock(return_value=[])
        results = await Year.all_for_guild(TEST_GUILD)
        assert results == []

    @pytest.mark.asyncio
    async def test_get_latest(self, mock_year_repo, make_year_doc):
        mock_year_repo.get_latest = AsyncMock(return_value=make_year_doc(year=10))
        result = await Year.get_latest(TEST_GUILD)
        assert result is not None
        assert result.year == 10

    @pytest.mark.asyncio
    async def test_get_latest_empty(self, mock_year_repo):
        mock_year_repo.get_latest = AsyncMock(return_value=None)
        result = await Year.get_latest(TEST_GUILD)
        assert result is None


# --- Lifecycle Methods ---


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_create_from_rollover(self, mock_year_repo):
        result = await Year.create_from_rollover(TEST_GUILD, 5, start_time=1704067200)
        assert isinstance(result, Year)
        assert result.guild == TEST_GUILD
        assert result.year == 5
        assert result.start_time == 1704067200
        assert result.end_time == 0
        assert result.duration == 0
        assert 'Year 5 PC' in result.formatted
        mock_year_repo.upsert.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_from_rollover_formatted_matches_format_year_line(self, mock_year_repo):
        from attubot.calendar import format_year_line

        result = await Year.create_from_rollover(TEST_GUILD, 7, start_time=100)
        assert result.formatted == format_year_line(7).lstrip('# ')

    @pytest.mark.asyncio
    async def test_finalize_sets_end_time_and_duration(self, mock_year_repo, make_year_doc):
        start = 1704067200
        end = start + (14 * SECONDS_PER_DAY)  # 14 days later
        mock_year_repo.get = AsyncMock(return_value=make_year_doc(year=3, start_time=start, end_time=0, duration=0))

        result = await Year.finalize(TEST_GUILD, 3, end_time=end)
        assert result is not None
        assert result.end_time == end
        assert result.duration == 14
        mock_year_repo.update.assert_called_once_with(TEST_GUILD, 3, end_time=end, duration=14)

    @pytest.mark.asyncio
    async def test_finalize_nonexistent_returns_none(self, mock_year_repo):
        mock_year_repo.get = AsyncMock(return_value=None)
        result = await Year.finalize(TEST_GUILD, 99, end_time=999)
        assert result is None
        mock_year_repo.update.assert_not_called()

    @pytest.mark.asyncio
    async def test_finalize_rounds_duration(self, mock_year_repo, make_year_doc):
        """Duration should be rounded to nearest day"""
        start = 1704067200
        end = start + int(14.6 * SECONDS_PER_DAY)  # 14.6 days
        mock_year_repo.get = AsyncMock(return_value=make_year_doc(year=1, start_time=start, end_time=0, duration=0))

        result = await Year.finalize(TEST_GUILD, 1, end_time=end)
        assert result is not None
        assert result.duration == 15  # round(14.6) = 15
