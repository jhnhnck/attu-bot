"""
AttuBot - Tests for /trees Commands
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import hashlib
import hmac
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from nova_core.client.core import config
from tests.conftest import test_user


# --- Helpers ---

_HMAC_SECRET = 'test-secret-key'  # noqa: S105 - test value only
_DEV_URL = 'http://attu-tree-dev:8000'
_PROD_URL = 'http://attu-tree:8000'


_ADMIN_ROLE_ID = 111111111
_USER_ROLE_ID = 222222222


def _make_trees_config(**overrides):
    defaults = {
        'hmac_secret': _HMAC_SECRET,
        'dev_base_url': _DEV_URL,
        'prod_base_url': _PROD_URL,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_guild_roles(**overrides):
    defaults = {
        'trees_admin_role': _ADMIN_ROLE_ID,
        'trees_user_role': _USER_ROLE_ID,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_response(status_code: int, body: dict | None = None) -> httpx.Response:
    import json as _json

    content = _json.dumps(body or {}).encode()
    return httpx.Response(status_code, content=content, headers={'content-type': 'application/json'})


# --- TestComingSoonGate ---


class TestComingSoonGate:
    async def test_non_owner_gets_coming_soon(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user, is_owner=False)
        config.owner_ids = set()

        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees._api_call', AsyncMock()):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('coming soon' in str(r['args']) for r in ctx._responses)

    async def test_owner_passes_through(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        config.owner_ids = {test_user}
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890

        mock_resp = _make_response(200, {'display_name': 'Test User'})
        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert not any('coming soon' in str(r['args']) for r in ctx._responses)

    async def test_autocomplete_returns_empty_for_non_owner(self):
        config.owner_ids = set()

        ctx = MagicMock()
        ctx.interaction = MagicMock()
        ctx.interaction.user = MagicMock()
        ctx.interaction.user.id = test_user
        ctx.value = ''

        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _tree_autocomplete

            result = await _tree_autocomplete(ctx)

        assert result == []


# --- TestRouteFor ---


class TestRouteFor:
    def setup_method(self):
        config.trees = _make_trees_config()

    def test_x_routes_to_dev(self):
        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _route_for

            assert _route_for('AX-123456') == _DEV_URL

    def test_z_routes_to_dev(self):
        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _route_for

            assert _route_for('AZ-123456') == _DEV_URL

    def test_other_letter_routes_to_prod(self):
        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _route_for

            for letter in 'ABCDEFGHJKLMNPQRSTUVWY':  # 22 prod chars (not I/O/X/Z)
                assert _route_for(f'A{letter}-000000') == _PROD_URL

    def test_malformed_short_code_routes_to_prod(self):
        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _route_for

            assert _route_for('A') == _PROD_URL
            assert _route_for('') == _PROD_URL

    def test_lowercase_code_handled(self):
        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _route_for

            assert _route_for('ax-123456') == _DEV_URL
            assert _route_for('ab-123456') == _PROD_URL


# --- TestSignRequest ---


class TestSignRequest:
    def test_signature_format(self):
        config.trees = _make_trees_config()

        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _sign

            body = b'{"code": "AB-123456"}'
            ts, sig = _sign(body)

        assert sig.startswith('sha256=')
        assert ts.isdigit()

    def test_signature_verifiable(self):
        config.trees = _make_trees_config()

        with patch('nova_core.commands.trees.config', config):
            from nova_core.commands.trees import _sign

            body = b'{"test": true}'
            ts, sig = _sign(body)

        payload = f'{ts}.'.encode() + body
        expected = hmac.new(_HMAC_SECRET.encode(), payload, hashlib.sha256).hexdigest()
        assert sig == f'sha256={expected}'


# --- TestExtractRoles ---


class TestExtractRoles:
    def setup_method(self):
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890
        config.guild = MagicMock(return_value=SimpleNamespace(roles=_make_guild_roles()))

    def _make_member(self, *role_ids):
        roles = []
        for rid in role_ids:
            r = MagicMock()
            r.id = rid
            roles.append(r)
        member = MagicMock()
        member.roles = roles
        return member

    def _make_bot(self, member):
        guild = MagicMock()
        guild.get_member = MagicMock(return_value=member)
        mock_bot = MagicMock()
        mock_bot.get_guild = MagicMock(return_value=guild)
        return mock_bot

    def test_admin_role_match(self):
        mock_bot = self._make_bot(self._make_member(_ADMIN_ROLE_ID))
        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result == ['admin']

    def test_user_role_match(self):
        mock_bot = self._make_bot(self._make_member(_USER_ROLE_ID))
        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result == ['user']

    def test_both_roles_match(self):
        mock_bot = self._make_bot(self._make_member(_ADMIN_ROLE_ID, _USER_ROLE_ID))
        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result == ['admin', 'user']

    def test_neither_role_match(self):
        mock_bot = self._make_bot(self._make_member(999999999))
        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result == []

    def test_roles_unconfigured(self):
        config.guild = MagicMock(return_value=SimpleNamespace(roles=_make_guild_roles(trees_admin_role=0, trees_user_role=0)))
        mock_bot = self._make_bot(self._make_member(_ADMIN_ROLE_ID, _USER_ROLE_ID))
        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result == []

    def test_member_not_in_primary_guild(self):
        guild = MagicMock()
        guild.get_member = MagicMock(return_value=None)
        mock_bot = MagicMock()
        mock_bot.get_guild = MagicMock(return_value=guild)

        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result is None

    def test_guild_unavailable(self):
        mock_bot = MagicMock()
        mock_bot.get_guild = MagicMock(return_value=None)

        with patch('nova_core.commands.trees.config', config), patch('nova_core.commands.trees.bot', mock_bot):
            from nova_core.commands.trees import _extract_roles

            result = _extract_roles(test_user)

        assert result is None


# --- TestTreesLink ---


class TestTreesLink:
    def setup_method(self):
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890
        config.owner_ids = {test_user}

    async def test_success(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(200, {'display_name': 'Haradar Karn'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert ctx.defer.called
        text = str(ctx._responses)
        assert 'Haradar Karn' in text
        assert 'linked as' in text

    async def test_code_expired(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(422, {'detail': 'code_expired'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('expired' in str(r['args']) for r in ctx._responses)
        assert any(r['kwargs'].get('ephemeral') for r in ctx._responses)

    async def test_code_already_used(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(422, {'detail': 'code_already_used'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('redeemed' in str(r['args']) for r in ctx._responses)

    async def test_code_not_found(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(422, {'detail': 'code_not_found'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any("don't recognize" in str(r['args']) for r in ctx._responses)

    async def test_network_timeout(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(side_effect=httpx.TimeoutException('timeout'))),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any("can't reach" in str(r['args']) for r in ctx._responses)

    async def test_connect_error(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(side_effect=httpx.ConnectError('refused'))),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any("can't reach" in str(r['args']) for r in ctx._responses)

    async def test_401_hmac_failure(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(401, {})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('keys' in str(r['args']) for r in ctx._responses)

    async def test_5xx_logs_and_notifies(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(500, {})

        mock_logger = MagicMock()
        mock_logger.error = MagicMock()
        mock_logger.debug = MagicMock()

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
            patch('nova_core.commands.trees.logger', mock_logger),
            patch('attu_logging.webhook.send_to_webhook', new_callable=AsyncMock) as mock_webhook,
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert mock_logger.error.called
        assert mock_webhook.called
        assert any('proper authorities' in str(r['args']) for r in ctx._responses)

    async def test_dev_url_used_for_x_code(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(200, {'display_name': 'Test'})
        captured_url = []

        async def capture_call(method, url, body=None):
            captured_url.append(url)
            return mock_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=capture_call),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AX-123456')

        assert captured_url[0].startswith(_DEV_URL)

    async def test_prod_url_used_for_non_xz_code(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(200, {'display_name': 'Test'})
        captured_url = []

        async def capture_call(method, url, body=None):
            captured_url.append(url)
            return mock_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=capture_call),
            patch('nova_core.commands.trees._extract_roles', return_value=['user']),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert captured_url[0].startswith(_PROD_URL)

    async def test_not_in_primary_guild(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._extract_roles', return_value=None),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('how are you even doing this' in str(r['args']) for r in ctx._responses)
        assert any(r['kwargs'].get('ephemeral') for r in ctx._responses)

    async def test_no_authorized_role(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._extract_roles', return_value=[]),
        ):
            from nova_core.commands.trees import trees_link

            await trees_link(ctx, code='AB-123456')

        assert any('write your island' in str(r['args']) for r in ctx._responses)
        assert any(r['kwargs'].get('ephemeral') for r in ctx._responses)


# --- TestTreesShow ---


class TestTreesShow:
    def setup_method(self):
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890
        config.owner_ids = {test_user}

    async def test_not_linked(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(404, {'detail': 'user_not_linked'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
        ):
            from nova_core.commands.trees import trees_show

            await trees_show(ctx)

        assert any("haven't linked" in str(r['args']) for r in ctx._responses)

    async def test_no_trees(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        mock_resp = _make_response(200, {'trees': []})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
        ):
            from nova_core.commands.trees import trees_show

            await trees_show(ctx)

        assert any('no trees' in str(r['args']) for r in ctx._responses)

    async def test_trees_present_renders_select_view(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        trees_data = [
            {'id': 'uuid-1', 'name': 'Akarian Royal House', 'role': 'owner', 'updated_at': '2026-01-01T00:00:00Z'},
            {'id': 'uuid-2', 'name': 'Haradar Family', 'role': 'editor', 'updated_at': '2026-01-01T00:00:00Z'},
        ]
        mock_resp = _make_response(200, {'trees': trees_data})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
        ):
            from nova_core.commands.trees import TreesShowView, trees_show

            await trees_show(ctx)

        # verify a view was passed to respond
        assert ctx._responses
        last = ctx._responses[-1]
        assert isinstance(last['kwargs'].get('view'), TreesShowView)

    async def test_network_error(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(side_effect=httpx.ConnectError('refused'))),
        ):
            from nova_core.commands.trees import trees_show

            await trees_show(ctx)

        assert any("can't reach" in str(r['args']) for r in ctx._responses)


# --- TestTreesShare ---


class TestTreesShare:
    def setup_method(self):
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890
        config.owner_ids = {test_user}

    def _make_target(self):
        target = MagicMock()
        target.id = 1111111111
        target.global_name = 'TargetUser'
        target.name = 'targetuser'
        target.mention = '<@1111111111>'
        return target

    async def test_success_with_view_link(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()

        grant_resp = _make_response(200, {'user_id': 'uuid-target', 'role': 'editor'})
        link_resp = _make_response(200, {'url': 'https://attuproject.org/trees/view/uuid-1'})
        list_resp = _make_response(200, {'trees': [{'id': 'uuid-1', 'name': 'Akarian Royal House', 'role': 'owner', 'updated_at': ''}]})

        call_count = 0

        async def multi_resp(method, url, body=None):
            nonlocal call_count
            call_count += 1
            if 'grants' in url and method == 'POST':
                return grant_resp
            if 'view-link' in url:
                return link_resp
            return list_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=multi_resp),
        ):
            from nova_core.commands.trees import trees_share

            await trees_share(ctx, tree='uuid-1', user=target, role='editor')

        text = str(ctx._responses)
        assert 'Akarian Royal House' in text or 'shared' in text

    async def test_not_owner_403(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()
        mock_resp = _make_response(403, {'detail': 'not_owner'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
        ):
            from nova_core.commands.trees import trees_share

            await trees_share(ctx, tree='uuid-1', user=target, role='editor')

        assert any('only share trees you own' in str(r['args']) for r in ctx._responses)
        assert any(r['kwargs'].get('ephemeral') for r in ctx._responses)

    async def test_tree_not_found_404(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()
        mock_resp = _make_response(404, {'detail': 'tree_not_found'})

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(return_value=mock_resp)),
        ):
            from nova_core.commands.trees import trees_share

            await trees_share(ctx, tree='uuid-1', user=target, role='editor')

        assert any("doesn't exist" in str(r['args']) for r in ctx._responses)

    async def test_network_error(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', AsyncMock(side_effect=httpx.ConnectError('refused'))),
        ):
            from nova_core.commands.trees import trees_share

            await trees_share(ctx, tree='uuid-1', user=target, role='editor')

        assert any("can't reach" in str(r['args']) for r in ctx._responses)


# --- TestTreesUnshare ---


class TestTreesUnshare:
    def setup_method(self):
        config.trees = _make_trees_config()
        config.primary_guild = 1234567890
        config.owner_ids = {test_user}

    def _make_target(self):
        target = MagicMock()
        target.id = 1111111111
        target.global_name = 'TargetUser'
        target.name = 'targetuser'
        target.mention = '<@1111111111>'
        return target

    async def test_success(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()

        list_resp = _make_response(200, {'trees': [{'id': 'uuid-1', 'name': 'Akarian Royal House', 'role': 'owner', 'updated_at': ''}]})
        delete_resp = _make_response(204, None)

        async def multi_resp(method, url, body=None):
            if method == 'DELETE':
                return delete_resp
            return list_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=multi_resp),
        ):
            from nova_core.commands.trees import trees_unshare

            await trees_unshare(ctx, tree='uuid-1', user=target)

        text = str(ctx._responses)
        assert 'removed' in text
        assert 'TargetUser' in text

    async def test_not_owner_403(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()

        list_resp = _make_response(200, {'trees': []})
        delete_resp = _make_response(403, {'detail': 'not_owner'})

        async def multi_resp(method, url, body=None):
            if method == 'DELETE':
                return delete_resp
            return list_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=multi_resp),
        ):
            from nova_core.commands.trees import trees_unshare

            await trees_unshare(ctx, tree='uuid-1', user=target)

        assert any('only unshare' in str(r['args']) for r in ctx._responses)

    async def test_tree_not_found_404(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        target = self._make_target()

        list_resp = _make_response(200, {'trees': []})
        delete_resp = _make_response(404, {'detail': 'tree_not_found'})

        async def multi_resp(method, url, body=None):
            if method == 'DELETE':
                return delete_resp
            return list_resp

        with (
            patch('nova_core.commands.trees.config', config),
            patch('nova_core.commands.trees._api_call', side_effect=multi_resp),
        ):
            from nova_core.commands.trees import trees_unshare

            await trees_unshare(ctx, tree='uuid-1', user=target)

        assert any("doesn't exist" in str(r['args']) for r in ctx._responses)
