"""
AttuBot - Ping/Pong Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Integration tests for the /ping and /pong commands
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import patch

import pytest


# --- /ping Command Tests ---


class TestPingCommand:
    @pytest.mark.asyncio
    async def test_ping_responds_pong(self, mock_ctx):
        """Test that /ping responds with 'Pong!' and latency"""
        from nova_core.client import command_ping

        mock_ctx.bot.latency = 0.042

        await command_ping(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'Pong!' in response
        assert '(42ms)' in response
        assert '<:rockball:1308981475114225694>' in response


# --- /pong Command Tests ---


class TestPongCommand:
    @pytest.mark.asyncio
    async def test_pong_owner_immediate_response(self, mock_ctx_factory):
        """Test that /pong responds immediately with mention for bot owner"""
        from nova_core.commands.debug import command_pong

        ctx = mock_ctx_factory(user_id=999, is_owner=True)
        # Mock config.is_owner to return True
        with patch('nova_core.commands.debug.config.is_owner', return_value=True):
            await command_pong(ctx)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert ctx.author.mention in response
        assert '<:rockball:1308981475114225694>' in response

    @pytest.mark.asyncio
    async def test_pong_non_owner_ping_response(self, mock_ctx_factory):
        """Test that /pong responds with 'Ping!' for non-owner and creates background task"""
        from unittest.mock import MagicMock

        from nova_core import tasks as tasks_module
        from nova_core.commands.debug import command_pong

        ctx = mock_ctx_factory(user_id=888, is_owner=False)

        # Create a mock scheduler with an add_job method
        mock_scheduler = MagicMock()

        # Mock config.is_owner to return False and the tasks module scheduler
        with patch('nova_core.commands.debug.config.is_owner', return_value=False), patch.object(tasks_module, 'scheduler', mock_scheduler):
            await command_pong(ctx)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert 'Ping!' in response
        assert '<:rockball:1308981475114225694>' in response

        # Verify a background task was created
        mock_scheduler.add_job.assert_called_once()
        call_args = mock_scheduler.add_job.call_args
        assert 'PongTask' in call_args[0][1]  # task name contains 'PongTask'
