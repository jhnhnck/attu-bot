"""
AttuBot - Permission Predicate Unit Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Compensation tests for the mock boundary in command tests: all command tests call
functions directly and bypass @commands.check decorators, so the predicate functions
(is_bot_owner, is_authorized_guild, has_announcements_role) are never executed by those
tests. This file covers the predicate logic directly.

See notes/testing.md "Mock compensation" for the full rationale.
"""

from unittest.mock import MagicMock

import discord

from attubot.client.util import has_announcements_role, is_authorized_guild, is_bot_owner
from tests.conftest import test_guild, test_user


_ROLE_ID = 111222333444


# ============================================================
# is_bot_owner
# ============================================================


class TestIsBotOwner:
    """unit: is_bot_owner predicate"""

    def test_returns_true_for_owner(self, mock_ctx_factory):
        from attubot.client.core import config

        config.owner_ids.add(test_user)
        ctx = mock_ctx_factory(user_id=test_user)
        assert is_bot_owner(ctx) is True

    def test_returns_false_for_non_owner(self, mock_ctx_factory):
        from attubot.client.core import config

        config.owner_ids.add(test_user)
        ctx = mock_ctx_factory(user_id=test_user + 1)
        assert is_bot_owner(ctx) is False

    def test_returns_false_when_owner_ids_empty(self, mock_ctx_factory):
        ctx = mock_ctx_factory(user_id=test_user)
        assert is_bot_owner(ctx) is False


# ============================================================
# is_authorized_guild
# ============================================================


class TestIsAuthorizedGuild:
    """unit: is_authorized_guild predicate"""

    def test_returns_true_for_authorized_guild(self, mock_ctx_factory, guild):
        # guild fixture registers test_guild in config.authorized_guilds
        ctx = mock_ctx_factory()
        assert is_authorized_guild(ctx) is True

    def test_returns_false_for_unauthorized_guild(self, mock_ctx_factory):
        ctx = mock_ctx_factory(guild_id=test_guild + 1)
        assert is_authorized_guild(ctx) is False


# ============================================================
# has_announcements_role
# ============================================================


class TestHasAnnouncementsRole:
    """unit: has_announcements_role predicate"""

    def test_returns_true_for_member_with_role(self, mock_ctx_factory, make_guild):
        gc = make_guild()
        gc.roles.announcements = _ROLE_ID

        role = MagicMock()
        role.id = _ROLE_ID

        ctx = mock_ctx_factory()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.roles = [role]

        assert has_announcements_role(ctx) is True

    def test_returns_false_for_member_without_role(self, mock_ctx_factory, make_guild):
        gc = make_guild()
        gc.roles.announcements = _ROLE_ID

        ctx = mock_ctx_factory()
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.roles = []

        assert has_announcements_role(ctx) is False

    def test_returns_false_when_role_unconfigured(self, mock_ctx_factory, guild):
        # default GuildRoles has announcements=0; predicate returns False early
        ctx = mock_ctx_factory()
        assert has_announcements_role(ctx) is False

    def test_returns_false_for_unauthorized_guild(self, mock_ctx_factory):
        # guild not in config at all; config.guild() raises; predicate catches and returns False
        ctx = mock_ctx_factory(guild_id=test_guild + 1)
        assert has_announcements_role(ctx) is False

    def test_returns_false_for_non_member_author(self, mock_ctx_factory, make_guild):
        # author is not a discord.Member (e.g. a User) - isinstance check fails
        gc = make_guild()
        gc.roles.announcements = _ROLE_ID

        ctx = mock_ctx_factory()
        # ctx.author is a plain MagicMock (no spec), so isinstance(author, discord.Member) is False
        assert has_announcements_role(ctx) is False


# ============================================================
# shift_hue
# ============================================================


class TestShiftHue:
    """unit: shift_hue helper"""

    def test_shifts_color(self):
        from attubot.client.util import shift_hue

        result = shift_hue('#ff0000')
        assert result != '#ff0000'
        assert result.startswith('#')
        assert len(result) == 7

    def test_360_degree_shift_is_identity(self):
        from attubot.client.util import shift_hue

        # 360-degree shift is a no-op for hue; with round() the integer values are stable
        assert shift_hue('#ff0000', degrees=360.0) == '#ff0000'
        assert shift_hue('#00ffff', degrees=360.0) == '#00ffff'
