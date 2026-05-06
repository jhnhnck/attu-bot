"""
AttuBot - Unit Tests for Family Tracking Module
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from doom_bot.client.families import get_family, get_viewer_url, is_family_file, list_families, save_family
from doom_bot.database.models import FamilyDocument


pytestmark = pytest.mark.unit


# ============================================================
# sample content
# ============================================================

_VALID_FAMILYSCRIPT = '# The Smith Family\n#\n# FamilyScript downloaded by John Smith\nDATA LINE\n'
_VALID_FAMILYSCRIPT_CRLF = '# The Smith Family\r\n#\r\n# FamilyScript downloaded by John Smith\r\nDATA LINE\r\n'
_VALID_GEDCOM = '0 HEAD\n1 SOUR Family Echo\n2 VERS 1.0\n'
_VALID_GEDCOM_CRLF = '0 HEAD\r\n1 SOUR Family Echo\r\n2 VERS 1.0\r\n'
_NOT_FAMILY = 'this is just some random text\nnothing to see here\n'
_EMPTY = ''


# ============================================================
# is_family_file()
# ============================================================


class TestIsFamilyFile:
    """unit: is_family_file correctly identifies FamilyScript and GEDCOM headers"""

    def test_valid_familyscript_returns_true(self):
        assert is_family_file(_VALID_FAMILYSCRIPT) is True

    def test_valid_familyscript_crlf_returns_true(self):
        assert is_family_file(_VALID_FAMILYSCRIPT_CRLF) is True

    def test_valid_gedcom_returns_true(self):
        assert is_family_file(_VALID_GEDCOM) is True

    def test_valid_gedcom_crlf_returns_true(self):
        assert is_family_file(_VALID_GEDCOM_CRLF) is True

    def test_non_family_content_returns_false(self):
        assert is_family_file(_NOT_FAMILY) is False

    def test_empty_content_returns_false(self):
        assert is_family_file(_EMPTY) is False

    def test_partial_header_returns_false(self):
        """header that starts correct but is incomplete"""
        assert is_family_file('# Some Name\n#\n# Not the right prefix\n') is False


# ============================================================
# get_viewer_url()
# ============================================================


class TestGetViewerUrl:
    """unit: get_viewer_url posts content to FamilyEcho and returns the temporary URL"""

    async def test_successful_response_returns_url(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'url': 'https://www.familyecho.com/?t=abc123'}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('doom_bot.client.families.httpx.AsyncClient', return_value=mock_client):
            result = await get_viewer_url('file content')

        assert result == 'https://www.familyecho.com/?t=abc123'
        mock_client.post.assert_awaited_once()

    async def test_api_error_in_body_raises_valueerror(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'error': 'invalid family data'}

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('doom_bot.client.families.httpx.AsyncClient', return_value=mock_client), pytest.raises(ValueError, match='FamilyEcho API error'):
            await get_viewer_url('bad content')

    async def test_missing_url_in_response_raises_valueerror(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {'status': 'ok'}  # no 'url' key

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('doom_bot.client.families.httpx.AsyncClient', return_value=mock_client), pytest.raises(ValueError, match='unexpected FamilyEcho API response'):
            await get_viewer_url('content')

    async def test_http_error_propagates(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            'server error',
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch('doom_bot.client.families.httpx.AsyncClient', return_value=mock_client), pytest.raises(httpx.HTTPStatusError):
            await get_viewer_url('content')


# ============================================================
# _get_repo() guard
# ============================================================


class TestGetRepoGuard:
    """unit: repo functions raise RuntimeError when repo is not initialized"""

    async def test_get_family_raises_when_repo_none(self):
        with patch('doom_bot.client.families._family_repo', None), pytest.raises(RuntimeError, match='family repo not initialized'):
            await get_family(123, 'test')

    async def test_save_family_raises_when_repo_none(self):
        doc = FamilyDocument(
            guild_id=123,
            name='test',
            display_name='Test',
            file_content='data',
            set_by=456,
            set_at=1000000,
        )
        with patch('doom_bot.client.families._family_repo', None), pytest.raises(RuntimeError, match='family repo not initialized'):
            await save_family(doc)

    async def test_list_families_raises_when_repo_none(self):
        with patch('doom_bot.client.families._family_repo', None), pytest.raises(RuntimeError, match='family repo not initialized'):
            await list_families(123)


# ============================================================
# get_family()
# ============================================================


class TestGetFamily:
    """unit: get_family delegates to repo with normalized name"""

    async def test_family_found(self):
        mock_repo = AsyncMock()
        expected = FamilyDocument(
            guild_id=123,
            name='smith',
            display_name='Smith',
            file_content='data',
            set_by=456,
            set_at=1000000,
        )
        mock_repo.get.return_value = expected

        with patch('doom_bot.client.families._family_repo', mock_repo):
            result = await get_family(123, 'Smith')

        assert result is expected
        mock_repo.get.assert_awaited_once_with(123, 'smith')

    async def test_family_not_found(self):
        mock_repo = AsyncMock()
        mock_repo.get.return_value = None

        with patch('doom_bot.client.families._family_repo', mock_repo):
            result = await get_family(123, 'unknown')

        assert result is None

    async def test_name_is_stripped_and_lowered(self):
        mock_repo = AsyncMock()
        mock_repo.get.return_value = None

        with patch('doom_bot.client.families._family_repo', mock_repo):
            await get_family(123, '  Jones  ')

        mock_repo.get.assert_awaited_once_with(123, 'jones')


# ============================================================
# save_family()
# ============================================================


class TestSaveFamily:
    """unit: save_family calls repo.upsert with the document"""

    async def test_successful_save(self):
        mock_repo = AsyncMock()
        doc = FamilyDocument(
            guild_id=123,
            name='smith',
            display_name='Smith',
            file_content='data',
            set_by=456,
            set_at=1000000,
        )

        with patch('doom_bot.client.families._family_repo', mock_repo):
            await save_family(doc)

        mock_repo.upsert.assert_awaited_once_with(doc)


# ============================================================
# list_families()
# ============================================================


class TestListFamilies:
    """unit: list_families returns all families for a guild"""

    async def test_with_results(self):
        mock_repo = AsyncMock()
        docs = [
            FamilyDocument(guild_id=123, name='smith', display_name='Smith', file_content='a', set_by=1, set_at=100),
            FamilyDocument(guild_id=123, name='jones', display_name='Jones', file_content='b', set_by=2, set_at=200),
        ]
        mock_repo.list_all.return_value = docs

        with patch('doom_bot.client.families._family_repo', mock_repo):
            result = await list_families(123)

        assert result == docs
        assert len(result) == 2
        mock_repo.list_all.assert_awaited_once_with(123)

    async def test_empty_result(self):
        mock_repo = AsyncMock()
        mock_repo.list_all.return_value = []

        with patch('doom_bot.client.families._family_repo', mock_repo):
            result = await list_families(123)

        assert result == []
