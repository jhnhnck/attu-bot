# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_commands_color | tests for the /color command."""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import MagicMock, patch

import pytest

from nova_core.client.core import config


# --- /color command tests ---


class TestColorCommand:
    @pytest.mark.asyncio
    async def test_color_returns_embed_with_hex(self, mock_ctx):
        """test that /color responds with an embed whose description contains the hex color"""
        from nova_core.commands.debug import command_color

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
        """test that /color responds ephemerally with a failure message when no theme is set"""
        from nova_core.commands.debug import command_color

        with patch.object(config, 'theme', None):
            await command_color(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'Failed:' in response['args'][0]
