"""
Tests for Year-aware epoch move functionality
"""

from datetime import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time

from attubot.calendar import move_epoch

class TestMoveEpochYearUpdates:
    """Test that move_epoch updates Year records with notes"""

    @pytest.mark.asyncio
    @freeze_time('2024-06-15 12:00:00')
    async def test_epoch_extend_adds_note(self, make_year):
        """When epoch is extended, Year record should be updated with note"""
        guild_id = 1234567890
        current_year = 5

        # Mock Year.get to return an existing year
        existing_year = make_year(guild=guild_id, year=current_year, start_time=1700000000, notes='')

        with patch('attubot.years.Year.get', new_callable=AsyncMock) as mock_get, \
             patch('attubot.years.Year.update', new_callable=AsyncMock) as mock_update, \
             patch('attubot.calendar.get_year_status') as mock_status, \
             patch('attubot.calendar.get_year_span', new_callable=AsyncMock) as mock_span, \
             patch('attubot.calendar.config') as mock_config:

            mock_get.return_value = existing_year
            mock_status.return_value = (150, current_year)  # 150 elapsed days
            mock_span.return_value = MagicMock(start_time=1700000000, end_time=1710000000, duration=365)

            # Mock config
            mock_guild_config = MagicMock()
            mock_guild_config.epoch.paused = False
            mock_guild_config.epoch.year = current_year
            mock_guild_config.epoch.time = 1700000000
            mock_guild_config.epoch.length = 365
            mock_guild_config.epoch.get_rollover_time.return_value = time(hour=0, minute=0)
            mock_guild_config.set_epoch = AsyncMock()
            mock_guild_config.set_year_length = AsyncMock()
            mock_config.primary.return_value = mock_guild_config
            mock_config.primary_guild = guild_id

            # Call move_epoch with a longer length (extend scenario)
            await move_epoch(400)

            # Verify Year.get was called
            mock_get.assert_called_once_with(guild_id, current_year)

            # Verify update was called with a note
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert 'notes' in call_kwargs
            assert 'Epoch extended' in call_kwargs['notes']
            assert 'Year 5' in call_kwargs['notes']

    @pytest.mark.asyncio
    @freeze_time('2024-06-15 12:00:00')
    async def test_epoch_shorten_adds_note(self, make_year):
        """When epoch is shortened, Year record should be updated with note"""
        guild_id = 1234567890
        current_year = 5

        existing_year = make_year(guild=guild_id, year=current_year, start_time=1700000000, notes='')

        with patch('attubot.years.Year.get', new_callable=AsyncMock) as mock_get, \
             patch('attubot.years.Year.update', new_callable=AsyncMock) as mock_update, \
             patch('attubot.calendar.get_year_status') as mock_status, \
             patch('attubot.calendar.get_year_span', new_callable=AsyncMock) as mock_span, \
             patch('attubot.calendar.config') as mock_config:

            mock_get.return_value = existing_year
            mock_status.return_value = (200, current_year)  # 200 elapsed days
            mock_span.return_value = MagicMock(start_time=1700000000, end_time=1731456000, duration=365)

            mock_guild_config = MagicMock()
            mock_guild_config.epoch.paused = False
            mock_guild_config.epoch.year = current_year
            mock_guild_config.epoch.time = 1700000000
            mock_guild_config.epoch.length = 365
            mock_guild_config.epoch.get_rollover_time.return_value = time(hour=0, minute=0)
            mock_guild_config.set_epoch = AsyncMock()
            mock_guild_config.set_year_length = AsyncMock()
            mock_config.primary.return_value = mock_guild_config
            mock_config.primary_guild = guild_id

            # Call move_epoch with a shorter length (shorten scenario - new length < elapsed)
            await move_epoch(100)

            # Verify update was called with a note
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert 'notes' in call_kwargs
            assert 'Epoch shortened' in call_kwargs['notes']

    @pytest.mark.asyncio
    @freeze_time('2024-06-15 12:00:00')
    async def test_epoch_resume_adds_note(self, make_year):
        """When epoch is resumed from pause, Year record should be updated with note"""
        guild_id = 1234567890
        current_year = 5

        existing_year = make_year(guild=guild_id, year=current_year, start_time=1700000000, notes='')

        with patch('attubot.years.Year.get', new_callable=AsyncMock) as mock_get, \
             patch('attubot.years.Year.update', new_callable=AsyncMock) as mock_update, \
             patch('attubot.calendar.get_year_status') as mock_status, \
             patch('attubot.calendar.get_year_span', new_callable=AsyncMock) as mock_span, \
             patch('attubot.calendar.config') as mock_config:

            mock_get.return_value = existing_year
            mock_status.return_value = (0, current_year)
            mock_span.return_value = MagicMock(start_time=1700000000, end_time=1731456000, duration=365)

            mock_guild_config = MagicMock()
            mock_guild_config.epoch.paused = True  # Paused state
            mock_guild_config.epoch.year = current_year
            mock_guild_config.epoch.time = 1700000000
            mock_guild_config.epoch.length = 365
            mock_guild_config.epoch.get_rollover_time.return_value = time(hour=0, minute=0)
            mock_guild_config.set_epoch = AsyncMock()
            mock_guild_config.set_year_length = AsyncMock()
            mock_config.primary.return_value = mock_guild_config
            mock_config.primary_guild = guild_id

            # Call move_epoch to resume
            await move_epoch(365)

            # Verify update was called with a note
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert 'notes' in call_kwargs
            assert 'Epoch resumed' in call_kwargs['notes']

    @pytest.mark.asyncio
    @freeze_time('2024-06-15 12:00:00')
    async def test_multiple_epoch_changes_append_notes(self, make_year):
        """Multiple epoch changes should append notes, not replace them"""
        guild_id = 1234567890
        current_year = 5

        # Year already has a note from previous change
        existing_year = make_year(
            guild=guild_id, year=current_year,
            start_time=1700000000, notes='Previous change note',
        )

        with patch('attubot.years.Year.get', new_callable=AsyncMock) as mock_get, \
             patch('attubot.years.Year.update', new_callable=AsyncMock) as mock_update, \
             patch('attubot.calendar.get_year_status') as mock_status, \
             patch('attubot.calendar.get_year_span', new_callable=AsyncMock) as mock_span, \
             patch('attubot.calendar.config') as mock_config:

            mock_get.return_value = existing_year
            mock_status.return_value = (150, current_year)
            mock_span.return_value = MagicMock(start_time=1700000000, end_time=1731456000, duration=365)

            mock_guild_config = MagicMock()
            mock_guild_config.epoch.paused = False
            mock_guild_config.epoch.year = current_year
            mock_guild_config.epoch.time = 1700000000
            mock_guild_config.epoch.length = 365
            mock_guild_config.epoch.get_rollover_time.return_value = time(hour=0, minute=0)
            mock_guild_config.set_epoch = AsyncMock()
            mock_guild_config.set_year_length = AsyncMock()
            mock_config.primary.return_value = mock_guild_config
            mock_config.primary_guild = guild_id

            # Call move_epoch
            await move_epoch(400)

            # Verify the note was appended, not replaced
            mock_update.assert_called_once()
            call_kwargs = mock_update.call_args[1]
            assert 'notes' in call_kwargs
            notes = call_kwargs['notes']
            assert 'Previous change note' in notes
            assert 'Epoch extended' in notes
            assert '\n' in notes  # Notes should be on separate lines

    @pytest.mark.asyncio
    @freeze_time('2024-06-15 12:00:00')
    async def test_no_crash_if_year_record_missing(self):
        """move_epoch should not crash if Year record doesn't exist yet"""
        guild_id = 1234567890
        current_year = 5

        with patch('attubot.years.Year.get', new_callable=AsyncMock) as mock_get, \
             patch('attubot.calendar.get_year_status') as mock_status, \
             patch('attubot.calendar.get_year_span', new_callable=AsyncMock) as mock_span, \
             patch('attubot.calendar.config') as mock_config:

            mock_get.return_value = None  # No Year record exists
            mock_status.return_value = (150, current_year)
            mock_span.return_value = MagicMock(start_time=1700000000, end_time=1731456000, duration=365)

            mock_guild_config = MagicMock()
            mock_guild_config.epoch.paused = False
            mock_guild_config.epoch.year = current_year
            mock_guild_config.epoch.time = 1700000000
            mock_guild_config.epoch.length = 365
            mock_guild_config.epoch.get_rollover_time.return_value = time(hour=0, minute=0)
            mock_guild_config.set_epoch = AsyncMock()
            mock_guild_config.set_year_length = AsyncMock()
            mock_config.primary.return_value = mock_guild_config
            mock_config.primary_guild = guild_id

            # Should not raise an exception
            await move_epoch(400)

            # Verify Year.get was called but nothing else failed
            mock_get.assert_called_once_with(guild_id, current_year)
