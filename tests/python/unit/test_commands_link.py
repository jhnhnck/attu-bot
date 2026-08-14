"""
AttuBot - Link Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nova_core.trees.documents import FamilyDocument
from tests.conftest import test_guild, test_user


# --- helpers ---


def _make_family_doc(name='stark', display_name='Stark', guild_id=test_guild, **kwargs):
    defaults = {
        'guild_id': guild_id,
        'name': name,
        'display_name': display_name,
        'file_content': '# family\n#\n# FamilyScript downloaded by test',
        'set_by': test_user,
        'set_at': 1700000000,
    }
    defaults.update(kwargs)
    return FamilyDocument(**defaults)


def _patch_guild():
    """patch config.guild to return a minimal guild config"""
    mock_guild_config = MagicMock()
    mock_guild_config.id = test_guild
    return patch('nova_core.commands.link.config.guild', return_value=mock_guild_config)


# --- /link family list ---


class TestFamilyList:
    @pytest.mark.asyncio
    async def test_empty_list_message(self, mock_ctx):
        """empty family list responds with helpful message"""
        from nova_core.commands.link import family_list

        with _patch_guild(), patch('nova_core.commands.link.list_families', new_callable=AsyncMock, return_value=[]):
            await family_list(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'no families registered' in response

    @pytest.mark.asyncio
    async def test_populated_list_sorted(self, mock_ctx):
        """family list shows entries sorted alphabetically by name"""
        from nova_core.commands.link import family_list

        families = [
            _make_family_doc(name='zephyr', display_name='Zephyr'),
            _make_family_doc(name='ark', display_name='Ark'),
            _make_family_doc(name='maple', display_name='Maple'),
        ]

        with _patch_guild(), patch('nova_core.commands.link.list_families', new_callable=AsyncMock, return_value=families):
            await family_list(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'registered families' in response
        # verify sorted order: ark < maple < zephyr
        ark_pos = response.index('Ark')
        maple_pos = response.index('Maple')
        zephyr_pos = response.index('Zephyr')
        assert ark_pos < maple_pos < zephyr_pos


# --- /link family view ---


class TestFamilyView:
    @pytest.mark.asyncio
    async def test_not_found_ephemeral(self, mock_ctx):
        """viewing a nonexistent family sends an ephemeral error"""
        from nova_core.commands.link import family_view

        with _patch_guild(), patch('nova_core.commands.link.get_family', new_callable=AsyncMock, return_value=None):
            await family_view(mock_ctx, name='nope')

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'no family named' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_shows_link(self, mock_ctx):
        """successful view shows the viewer url"""
        from nova_core.commands.link import family_view

        doc = _make_family_doc()
        viewer_url = 'https://www.familyecho.com/view/abc123'

        with (
            _patch_guild(),
            patch('nova_core.commands.link.get_family', new_callable=AsyncMock, return_value=doc),
            patch('nova_core.commands.link.get_viewer_url', new_callable=AsyncMock, return_value=viewer_url),
        ):
            await family_view(mock_ctx, name='stark')

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert viewer_url in response
        assert 'Stark' in response

    @pytest.mark.asyncio
    async def test_api_failure_ephemeral(self, mock_ctx):
        """api failure sends an ephemeral error"""
        from nova_core.commands.link import family_view

        doc = _make_family_doc()

        with (
            _patch_guild(),
            patch('nova_core.commands.link.get_family', new_callable=AsyncMock, return_value=doc),
            patch('nova_core.commands.link.get_viewer_url', new_callable=AsyncMock, side_effect=Exception('network error')),
        ):
            await family_view(mock_ctx, name='stark')

        # two calls: first the defer, then the error response
        assert len(mock_ctx._responses) == 1
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'could not generate viewer link' in mock_ctx._responses[0]['args'][0]


# --- /link family set ---


class TestFamilySet:
    @pytest.mark.asyncio
    async def test_invalid_link_ephemeral(self, mock_ctx):
        """non-discord link sends an ephemeral error"""
        from nova_core.commands.link import family_set

        with _patch_guild():
            await family_set(mock_ctx, name='test', message_link='https://example.com/not-a-link')

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'not look like a valid discord message link' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_no_attachment_ephemeral(self, mock_ctx):
        """message with no .txt/.ged attachment sends an ephemeral error"""
        from nova_core.commands.link import family_set

        # mock fetching a message that has no relevant attachments
        mock_msg = MagicMock()
        mock_msg.attachments = [MagicMock(filename='image.png')]

        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg)

        with (
            _patch_guild(),
            patch('nova_core.commands.link.bot') as mock_bot,
        ):
            mock_bot.get_channel = MagicMock(return_value=mock_channel)
            await family_set(mock_ctx, name='test', message_link='https://discord.com/channels/111/222/333')

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'no .txt or .ged file found' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_saves_and_responds(self, mock_ctx):
        """valid link with valid attachment saves the family and responds"""
        from nova_core.commands.link import family_set

        mock_attachment = MagicMock()
        mock_attachment.filename = 'family.txt'
        mock_attachment.read = AsyncMock(return_value=b'# family\n#\n# FamilyScript downloaded by test')

        mock_msg = MagicMock()
        mock_msg.attachments = [mock_attachment]

        mock_channel = MagicMock()
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg)

        with (
            _patch_guild(),
            patch('nova_core.commands.link.bot') as mock_bot,
            patch('nova_core.commands.link.is_family_file', return_value=True),
            patch('nova_core.commands.link.save_family', new_callable=AsyncMock) as mock_save,
        ):
            mock_bot.get_channel = MagicMock(return_value=mock_channel)
            await family_set(mock_ctx, name='Stark', message_link='https://discord.com/channels/111/222/333')

        mock_save.assert_called_once()
        saved_doc = mock_save.call_args[0][0]
        assert saved_doc.name == 'stark'
        assert saved_doc.display_name == 'Stark'

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'registered family' in response
        assert 'Stark' in response


# --- /link family upload ---


class TestFamilyUpload:
    @pytest.mark.asyncio
    async def test_invalid_file_ephemeral(self, mock_ctx):
        """uploading a non-family file sends an ephemeral error"""
        from nova_core.commands.link import family_upload

        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=b'this is not a family file')

        with (
            _patch_guild(),
            patch('nova_core.commands.link.is_family_file', return_value=False),
        ):
            await family_upload(mock_ctx, name='test', file=mock_file)

        mock_ctx.respond.assert_called_once()
        kwargs = mock_ctx._responses[0]['kwargs']
        assert kwargs.get('ephemeral') is True
        assert 'does not look like a FamilyScript' in mock_ctx._responses[0]['args'][0]

    @pytest.mark.asyncio
    async def test_success_saves_and_responds(self, mock_ctx):
        """valid upload saves the family and responds with success"""
        from nova_core.commands.link import family_upload

        content = '# family\n#\n# FamilyScript downloaded by test'
        mock_file = MagicMock()
        mock_file.read = AsyncMock(return_value=content.encode('utf-8'))

        with (
            _patch_guild(),
            patch('nova_core.commands.link.is_family_file', return_value=True),
            patch('nova_core.commands.link.save_family', new_callable=AsyncMock) as mock_save,
        ):
            await family_upload(mock_ctx, name='Maple', file=mock_file)

        mock_save.assert_called_once()
        saved_doc = mock_save.call_args[0][0]
        assert saved_doc.name == 'maple'
        assert saved_doc.display_name == 'Maple'
        assert saved_doc.file_content == content

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]['args'][0]
        assert 'registered family' in response
        assert 'Maple' in response
