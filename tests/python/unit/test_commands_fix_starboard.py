"""
AttuBot - Fix Starboard Command Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.commands.fix import fix_starboard_purge
from tests.conftest import TEST_CHANNEL, TEST_GUILD

MSG_ID = 7771234567890


@pytest.mark.asyncio
async def test_purge_rejects_invalid_link(mock_ctx_factory):
    """purge responds ephemeral when given a non-discord message link"""
    ctx = mock_ctx_factory()

    await fix_starboard_purge(ctx, message_link='not-a-link')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'Invalid' in ctx._responses[0]['args'][0]


@pytest.mark.asyncio
async def test_purge_repo_not_initialized(mock_ctx_factory):
    """purge responds ephemeral when the starboard repo is unavailable"""
    ctx = mock_ctx_factory()

    with patch('attubot.commands.fix._get_sb_repo', side_effect=RuntimeError('no repo')):
        await fix_starboard_purge(ctx, message_link=f'https://discord.com/channels/{TEST_GUILD}/{TEST_CHANNEL}/{MSG_ID}')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'not initialized' in ctx._responses[0]['args'][0]


@pytest.mark.asyncio
async def test_purge_entry_not_found(mock_ctx_factory):
    """purge responds ephemeral when the message has no starboard entry"""
    ctx = mock_ctx_factory()

    mock_repo = AsyncMock()
    mock_repo.get = AsyncMock(return_value=None)

    with patch('attubot.commands.fix._get_sb_repo', return_value=mock_repo):
        await fix_starboard_purge(ctx, message_link=f'https://discord.com/channels/{TEST_GUILD}/{TEST_CHANNEL}/{MSG_ID}')

    assert ctx._responses[0]['kwargs'].get('ephemeral') is True
    assert 'No starboard entry found' in ctx._responses[0]['args'][0]
