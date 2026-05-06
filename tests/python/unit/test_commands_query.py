"""
AttuBot - Query Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for /query pins command from query.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from discord import MessageType

from tests.conftest import test_guild


# --- Async Iterator Helper ---


class AsyncIterator:
    """helper to make a list behave as an async iterator for channel.history()"""

    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


# --- /query pins Command Tests ---


class TestQueryPinsCommand:
    @pytest.mark.asyncio
    async def test_pins_no_results(self, mock_ctx, guild):
        """test /query pins with no pin_add messages found"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator([]))

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)), patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span), patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)):
            await query_pins(mock_ctx, channel=mock_channel)

        # should respond with header but no year sections
        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Pins in' in response
        # no follow-up messages since no pins found
        mock_ctx.channel.send.assert_not_called()

    @pytest.mark.asyncio
    async def test_pins_single_pin_found(self, mock_ctx, guild):
        """test /query pins with one pin_add message"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        # create a mock pin_add message
        mock_message = MagicMock()
        mock_message.type = MessageType.pins_add
        mock_message.jump_url = 'https://discord.com/channels/123/456/789'
        mock_message.reference = MagicMock()
        mock_message.reference.channel_id = 456
        mock_message.reference.message_id = 100

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator([mock_message]))
        mock_ctx.channel.send = AsyncMock()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with (
            patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)),
            patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span),
            patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)),
            patch('doom_bot.commands.query.format_message_link', return_value='https://discord.com/channels/123/456/100'),
        ):
            await query_pins(mock_ctx, channel=mock_channel)

        # should respond with header
        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Pins in' in response

        # should send one year section with the pin
        mock_ctx.channel.send.assert_called_once()
        send_args = mock_ctx.channel.send.call_args[0][0]
        assert 'Year 1 PC' in send_args
        assert 'https://discord.com/channels/123/456/789' in send_args
        assert 'https://discord.com/channels/123/456/100' in send_args

    @pytest.mark.asyncio
    async def test_pins_multiple_pins_found(self, mock_ctx, guild):
        """test /query pins with multiple pin_add messages in one year"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        # create multiple mock pin_add messages
        mock_messages = []
        for i in range(3):
            msg = MagicMock()
            msg.type = MessageType.pins_add
            msg.jump_url = f'https://discord.com/channels/123/456/{700 + i}'
            msg.reference = MagicMock()
            msg.reference.channel_id = 456
            msg.reference.message_id = 100 + i
            mock_messages.append(msg)

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator(mock_messages))
        mock_ctx.channel.send = AsyncMock()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with (
            patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)),
            patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span),
            patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)),
            patch('doom_bot.commands.query.format_message_link', side_effect=[f'https://discord.com/channels/123/456/{100 + i}' for i in range(3)]),
        ):
            await query_pins(mock_ctx, channel=mock_channel)

        mock_ctx.channel.send.assert_called_once()
        send_args = mock_ctx.channel.send.call_args[0][0]
        # all three pins should appear
        for i in range(3):
            assert f'https://discord.com/channels/123/456/{700 + i}' in send_args
            assert f'https://discord.com/channels/123/456/{100 + i}' in send_args

    @pytest.mark.asyncio
    async def test_pins_mixed_message_types(self, mock_ctx, guild):
        """test /query pins filters only pin_add messages from mixed history"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        # create a mix of message types
        pin_msg = MagicMock()
        pin_msg.type = MessageType.pins_add
        pin_msg.jump_url = 'https://discord.com/channels/123/456/789'
        pin_msg.reference = MagicMock()
        pin_msg.reference.channel_id = 456
        pin_msg.reference.message_id = 100

        normal_msg = MagicMock()
        normal_msg.type = MessageType.default

        join_msg = MagicMock()
        join_msg.type = MessageType.new_member

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator([normal_msg, pin_msg, join_msg]))
        mock_ctx.channel.send = AsyncMock()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with (
            patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)),
            patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span),
            patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)),
            patch('doom_bot.commands.query.format_message_link', return_value='https://discord.com/channels/123/456/100'),
        ):
            await query_pins(mock_ctx, channel=mock_channel)

        # only one pin should be found
        mock_ctx.channel.send.assert_called_once()
        send_args = mock_ctx.channel.send.call_args[0][0]
        assert 'https://discord.com/channels/123/456/789' in send_args

    @pytest.mark.asyncio
    async def test_pins_multiple_years(self, mock_ctx, guild):
        """test /query pins iterates over multiple years"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        # pin in year 1 only, none in year 2
        pin_msg = MagicMock()
        pin_msg.type = MessageType.pins_add
        pin_msg.jump_url = 'https://discord.com/channels/123/456/789'
        pin_msg.reference = MagicMock()
        pin_msg.reference.channel_id = 456
        pin_msg.reference.message_id = 100

        call_count = 0

        def history_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return AsyncIterator([pin_msg])
            return AsyncIterator([])

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(side_effect=history_side_effect)
        mock_ctx.channel.send = AsyncMock()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with (
            patch('doom_bot.commands.query.get_year_status', return_value=(7, 2)),
            patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span),
            patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)),
            patch('doom_bot.commands.query.format_message_link', return_value='https://discord.com/channels/123/456/100'),
        ):
            await query_pins(mock_ctx, channel=mock_channel)

        # should call history twice (year 1 and year 2)
        assert mock_channel.history.call_count == 2
        # only year 1 had pins, so only one send
        mock_ctx.channel.send.assert_called_once()
        send_args = mock_ctx.channel.send.call_args[0][0]
        assert 'Year 1 PC' in send_args

    @pytest.mark.asyncio
    async def test_pins_message_reference_without_id(self, mock_ctx, guild):
        """test /query pins handles message_id being None (falls back to 0)"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        pin_msg = MagicMock()
        pin_msg.type = MessageType.pins_add
        pin_msg.jump_url = 'https://discord.com/channels/123/456/789'
        pin_msg.reference = MagicMock()
        pin_msg.reference.channel_id = 456
        pin_msg.reference.message_id = None  # no message_id

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator([pin_msg]))
        mock_ctx.channel.send = AsyncMock()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with (
            patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)),
            patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span),
            patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)),
            patch('doom_bot.commands.query.format_message_link', return_value='https://discord.com/channels/123/456/0') as mock_format,
        ):
            await query_pins(mock_ctx, channel=mock_channel)

        # format_message_link should receive 0 for the message_id
        mock_format.assert_called_once_with(test_guild, 456, 0)

    @pytest.mark.asyncio
    async def test_pins_channel_header_format(self, mock_ctx, guild):
        """test /query pins initial response includes channel mention"""
        from doom_bot.client.calendar import AttuYearSpan
        from doom_bot.commands.query import query_pins

        mock_channel = MagicMock()
        mock_channel.id = 6666666666
        mock_channel.name = 'test-pins'
        mock_channel.history = MagicMock(return_value=AsyncIterator([]))

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('doom_bot.commands.query.get_year_status', return_value=(7, 1)), patch('doom_bot.commands.query.get_year_span', new_callable=AsyncMock, return_value=mock_span), patch('doom_bot.commands.query.snowflake_time', return_value=datetime(2020, 1, 1)):
            await query_pins(mock_ctx, channel=mock_channel)

        response = mock_ctx._responses[0]['args'][0]
        # header should contain channel id reference
        assert f'<#{mock_channel.id}>' in response
