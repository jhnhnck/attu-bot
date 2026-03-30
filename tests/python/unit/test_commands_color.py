"""
AttuBot - Color Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Tests for the /color command from commands/debug.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import MagicMock, patch

import pytest

from attubot import config


# --- /color Command Tests ---


class TestColorCommand:
    @pytest.mark.asyncio
    async def test_color_returns_embed_with_hex(self, mock_ctx):
        """Test that /color responds with an embed whose description contains the hex color"""
        from attubot.commands.debug import command_color

        mock_theme = MagicMock()
        mock_theme.bot_color = '#1a2b3c'

        with patch.object(config, 'theme', mock_theme):
            await command_color(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        embed = response['kwargs']['embed']
        assert embed.title == 'Bot Color'
        assert '#1a2b3c' in embed.description

    @pytest.mark.asyncio
    async def test_color_no_theme_ephemeral_error(self, mock_ctx):
        """Test that /color responds ephemerally with a failure message when no theme is set"""
        from attubot.commands.debug import command_color

        with patch.object(config, 'theme', None):
            await command_color(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'Failed:' in response['args'][0]
