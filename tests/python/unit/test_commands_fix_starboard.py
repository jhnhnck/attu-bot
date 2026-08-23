# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_commands_fix_starboard | tests for fix starboard purge command."""

from unittest.mock import AsyncMock, patch

import pytest

from nova_core.commands.fix import fix_starboard_purge
from tests.conftest import test_channel, test_guild


msg_id = 7771234567890


@pytest.mark.asyncio
async def test_purge_rejects_invalid_link(mock_ctx_factory):
    """purge responds ephemeral when given a non-discord message link"""
    ctx = mock_ctx_factory()

    await fix_starboard_purge(ctx, message_link='not-a-link')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'Failed' in ctx._responses[0]['args'][0]


@pytest.mark.asyncio
async def test_purge_repo_not_initialized(mock_ctx_factory):
    """purge responds ephemeral when the starboard repo is unavailable"""
    ctx = mock_ctx_factory()

    with patch('nova_core.commands.fix._get_sb_repo', side_effect=RuntimeError('no repo')):
        await fix_starboard_purge(ctx, message_link=f'https://discord.com/channels/{test_guild}/{test_channel}/{msg_id}')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'not initialized' in ctx._responses[0]['args'][0]


@pytest.mark.asyncio
async def test_purge_entry_not_found(mock_ctx_factory):
    """purge responds ephemeral when the message has no starboard entry"""
    ctx = mock_ctx_factory()

    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=None)
    mock_repo.get_by_starboard_message = AsyncMock(return_value=None)

    with patch('nova_core.commands.fix._get_sb_repo', return_value=mock_repo):
        await fix_starboard_purge(ctx, message_link=f'https://discord.com/channels/{test_guild}/{test_channel}/{msg_id}')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'no starboard entry found for message' in ctx._responses[0]['args'][0]
