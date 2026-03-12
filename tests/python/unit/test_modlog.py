"""
AttuBot - Tests for moderation log handlers
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.config import GuildChannels


TEST_GUILD = 1234567890
TEST_USER = 9876543210
TEST_LOGS = 1111111111


def _make_logs_channel():
    channel = AsyncMock()
    channel.send = AsyncMock()
    return channel


def _make_guild():
    guild = MagicMock()
    guild.id = TEST_GUILD
    return guild


def _make_member(bot: bool = False):
    member = MagicMock()
    member.id = TEST_USER
    member.bot = bot
    member.mention = f'<@{TEST_USER}>'
    member.name = 'TestUser'
    member.global_name = 'TestGlobal'
    member.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    member.joined_at = datetime(2024, 1, 2, tzinfo=UTC)
    member.display_avatar = MagicMock(url='https://example.com/avatar.png')
    member.guild = _make_guild()
    member.roles = []
    member.nick = None
    member.communication_disabled_until = None
    return member


def _make_role(role_id=2222, name='Role', color='red', mention='@Role', position=1):
    role = MagicMock()
    role.id = role_id
    role.name = name
    role.color = color
    role.mention = mention
    role.position = position
    role.is_default = MagicMock(return_value=False)
    role.guild = _make_guild()
    role.hoist = False
    role.mentionable = False
    role.permissions = MagicMock(value=0)
    return role


def _make_channel(channel_id=4444, name='general', channel_type='text', category=None):
    channel = MagicMock()
    channel.id = channel_id
    channel.name = name
    channel.mention = f'<#{channel_id}>'
    channel.type = channel_type
    channel.category = category
    channel.guild = _make_guild()
    channel.topic = None
    channel.category_id = None
    channel.slowmode_delay = 0
    channel.nsfw = False
    return channel


def _make_emoji(emoji_id=7777, name='doom'):
    emoji = MagicMock()
    emoji.id = emoji_id
    emoji.name = name
    emoji.__str__ = MagicMock(return_value=f':{name}:')
    return emoji


def _make_audit_entry(target_id: int, bot: bool = False):
    entry = MagicMock()
    target = MagicMock()
    target.id = target_id
    entry.target = target
    user = MagicMock()
    user.bot = bot
    entry.user = user
    return entry


def _make_audit_log(entries: list[MagicMock]):
    async def _iter():
        for entry in entries:
            yield entry

    return _iter()


@pytest.fixture
def guild_with_logs(make_guild):
    guild = make_guild(guild_id=TEST_GUILD)
    guild.channels = GuildChannels(logs=TEST_LOGS)
    return guild


class TestMemberLogs:
    async def test_member_join_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_join

        member = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_join(member)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Joined'

    async def test_member_join_skips_bots(self, guild_with_logs):
        from attubot.client.modlog import on_member_join

        member = _make_member(bot=True)
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_join(member)

        logs_channel.send.assert_not_called()

    async def test_member_leave_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_remove

        member = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_remove(member)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Left'

    async def test_member_ban_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_ban

        guild = _make_guild()
        user = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_ban(guild, user)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Banned'

    async def test_member_unban_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_unban

        guild = _make_guild()
        user = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_unban(guild, user)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Unbanned'


class TestChannelLogs:
    async def test_channel_create_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_channel_create

        channel = _make_channel()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_channel_create(channel)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Channel Created'

    async def test_channel_create_skips_bot_audit(self, guild_with_logs):
        from attubot.client.modlog import on_guild_channel_create

        channel = _make_channel()
        logs_channel = _make_logs_channel()
        channel.guild.audit_logs = MagicMock(return_value=_make_audit_log([_make_audit_entry(channel.id, bot=True)]))

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_channel_create(channel)

        logs_channel.send.assert_not_called()

    async def test_channel_delete_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_channel_delete

        channel = _make_channel()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_channel_delete(channel)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Channel Deleted'

    async def test_channel_update_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_channel_update

        before = _make_channel(name='old')
        after = _make_channel(name='new')
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_channel_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Channel Updated'


class TestRoleLogs:
    async def test_role_create_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_role_create

        role = _make_role()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_role_create(role)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Role Created'

    async def test_role_create_skips_bot_audit(self, guild_with_logs):
        from attubot.client.modlog import on_guild_role_create

        role = _make_role()
        logs_channel = _make_logs_channel()
        role.guild.audit_logs = MagicMock(return_value=_make_audit_log([_make_audit_entry(role.id, bot=True)]))

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_role_create(role)

        logs_channel.send.assert_not_called()

    async def test_role_delete_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_role_delete

        role = _make_role()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_role_delete(role)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Role Deleted'

    async def test_role_update_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_role_update

        before = _make_role(name='old')
        after = _make_role(name='new')
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_role_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Role Updated'


class TestMemberUpdateLogs:
    async def test_nickname_change_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.nick = 'NewNick'
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Nickname Changed'

    async def test_role_add_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.roles = [_make_role(role_id=10, mention='@new')]
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Role Added'

    async def test_role_remove_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        before.roles = [_make_role(role_id=10, mention='@old')]
        after = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Role Removed'

    async def test_timeout_change_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.communication_disabled_until = datetime(2024, 1, 3, tzinfo=UTC)
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Member Timeout Updated'


class TestMemberAvatarIcons:
    """verify that member embeds include the author icon (profile picture)"""

    AVATAR_URL = 'https://example.com/avatar.png'

    async def test_member_join_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_join

        member = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_join(member)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_member_leave_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_remove

        member = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_remove(member)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_member_ban_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_ban

        guild = _make_guild()
        user = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_ban(guild, user)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_member_unban_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_unban

        guild = _make_guild()
        user = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_unban(guild, user)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_nick_change_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.nick = 'NewNick'
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_role_add_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.roles = [_make_role(role_id=10, mention='@new')]
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_role_remove_has_author_icon(self, guild_with_logs):
        from attubot.client.modlog import on_member_update

        before = _make_member()
        before.roles = [_make_role(role_id=10, mention='@old')]
        after = _make_member()
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL

    async def test_timeout_has_author_icon(self, guild_with_logs):
        from datetime import UTC, datetime

        from attubot.client.modlog import on_member_update

        before = _make_member()
        after = _make_member()
        after.communication_disabled_until = datetime(2024, 1, 3, tzinfo=UTC)
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_member_update(before, after)

        embed = logs_channel.send.call_args[1]['embed']
        assert embed.author.icon_url == self.AVATAR_URL


class TestEmojiLogs:
    async def test_emoji_create_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_emojis_update

        guild = _make_guild()
        before = []
        after = [_make_emoji()]
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_emojis_update(guild, before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Emoji Created'

    async def test_emoji_create_skips_bot_audit(self, guild_with_logs):
        from attubot.client.modlog import on_guild_emojis_update

        guild = _make_guild()
        emoji = _make_emoji()
        before = []
        after = [emoji]
        logs_channel = _make_logs_channel()
        guild.audit_logs = MagicMock(return_value=_make_audit_log([_make_audit_entry(emoji.id, bot=True)]))

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_emojis_update(guild, before, after)

        logs_channel.send.assert_not_called()

    async def test_emoji_delete_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_emojis_update

        guild = _make_guild()
        emoji = _make_emoji()
        before = [emoji]
        after = []
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_emojis_update(guild, before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Emoji Deleted'

    async def test_emoji_rename_sends_embed(self, guild_with_logs):
        from attubot.client.modlog import on_guild_emojis_update

        guild = _make_guild()
        before = [_make_emoji(name='old')]
        after = [_make_emoji(name='new')]
        logs_channel = _make_logs_channel()

        with patch('attubot.client.modlog._get_logs_channel', return_value=logs_channel):
            await on_guild_emojis_update(guild, before, after)

        logs_channel.send.assert_called_once()
        embed = logs_channel.send.call_args[1]['embed']
        assert embed.title == 'Emoji Renamed'
