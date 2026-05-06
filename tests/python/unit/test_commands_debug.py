"""
AttuBot - Debug Command Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

Unit tests for slash commands and helper functions in commands/debug.py
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest


# --- helper: _embed_summary ---


class TestEmbedSummary:
    def test_full_embed(self):
        """test _embed_summary with title, description, fields, and image"""
        from attubot.commands.debug import _embed_summary

        embed = discord.Embed(title='Hello', description='World')
        embed.add_field(name='f1', value='v1')
        embed.add_field(name='f2', value='v2')
        embed.set_image(url='https://example.com/img.png')

        name, value = _embed_summary(embed, 1)

        assert name == 'embed 1 [rich]'
        assert '**Hello**' in value
        assert 'World' in value
        assert '2 field(s)' in value
        assert 'https://example.com/img.png' in value

    def test_empty_embed(self):
        """test _embed_summary with a completely empty embed returns *empty*"""
        from attubot.commands.debug import _embed_summary

        embed = discord.Embed()
        name, value = _embed_summary(embed, 3)

        assert name == 'embed 3 [rich]'
        assert value == '*empty*'

    def test_long_description_truncated(self):
        """test _embed_summary truncates descriptions over 120 chars"""
        from attubot.commands.debug import _embed_summary

        long_text = 'a' * 200
        embed = discord.Embed(description=long_text)

        _, value = _embed_summary(embed, 0)

        assert value.endswith('...')
        assert len(value) <= 124  # 120 chars + '...'

    def test_title_only(self):
        """test _embed_summary with just a title"""
        from attubot.commands.debug import _embed_summary

        embed = discord.Embed(title='Only Title')
        _name, value = _embed_summary(embed, 5)

        assert '**Only Title**' in value
        assert 'field(s)' not in value


# --- helper: _message_dump ---


class TestMessageDump:
    def _make_message(self, *, content='hello', embed_count=0, attachment_count=0, reaction_count=0, sticker_count=0):
        """build a mock discord.Message with configurable sub-objects"""
        msg = MagicMock(spec=discord.Message)
        msg.id = 111222333
        msg.content = content
        msg.pinned = False
        msg.created_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        msg.edited_at = None
        msg.jump_url = 'https://discord.com/channels/1/2/3'

        # author
        msg.author = MagicMock()
        msg.author.id = 42
        msg.author.__str__ = lambda self: 'TestAuthor#0001'
        msg.author.display_avatar = MagicMock()
        msg.author.display_avatar.url = 'https://cdn.example.com/avatar.png'

        # embeds
        msg.embeds = [MagicMock(spec=discord.Embed) for _ in range(embed_count)]
        for e in msg.embeds:
            e.to_dict.return_value = {'type': 'rich', 'title': 'e'}

        # attachments
        msg.attachments = []
        for i in range(attachment_count):
            att = MagicMock()
            att.id = 9000 + i
            att.filename = f'file_{i}.png'
            att.url = f'https://cdn.example.com/file_{i}.png'
            msg.attachments.append(att)

        # reactions
        msg.reactions = []
        for i in range(reaction_count):
            rxn = MagicMock()
            rxn.emoji = f'emoji_{i}'
            rxn.count = i + 1
            msg.reactions.append(rxn)

        # stickers
        msg.stickers = []
        for i in range(sticker_count):
            stk = MagicMock()
            stk.id = 7000 + i
            stk.name = f'sticker_{i}'
            msg.stickers.append(stk)

        return msg

    def test_basic_serialization(self):
        """test _message_dump produces expected keys and values"""
        from attubot.commands.debug import _message_dump

        msg = self._make_message()
        result = _message_dump(msg, channel_id=222, guild_id=333)

        assert result['id'] == '111222333'
        assert result['author']['id'] == '42'
        assert result['author']['name'] == 'TestAuthor#0001'
        assert result['channel_id'] == '222'
        assert result['guild_id'] == '333'
        assert result['content'] == 'hello'
        assert result['pinned'] is False
        assert result['edited_at'] is None
        assert result['embeds'] == []
        assert result['attachments'] == []
        assert result['reactions'] == []
        assert result['stickers'] == []

    def test_with_all_sub_objects(self):
        """test _message_dump includes embeds, attachments, reactions, stickers"""
        from attubot.commands.debug import _message_dump

        msg = self._make_message(embed_count=2, attachment_count=1, reaction_count=1, sticker_count=1)
        msg.edited_at = datetime(2024, 6, 15, 13, 0, 0, tzinfo=UTC)

        result = _message_dump(msg, channel_id=222, guild_id=333)

        assert len(result['embeds']) == 2
        assert result['embeds'][0] == {'type': 'rich', 'title': 'e'}
        assert len(result['attachments']) == 1
        assert result['attachments'][0]['filename'] == 'file_0.png'
        assert len(result['reactions']) == 1
        assert result['reactions'][0]['emoji'] == 'emoji_0'
        assert result['reactions'][0]['count'] == 1
        assert len(result['stickers']) == 1
        assert result['stickers'][0]['name'] == 'sticker_0'
        assert result['edited_at'] is not None

    def test_output_is_json_serializable(self):
        """test _message_dump output round-trips through json"""
        from attubot.commands.debug import _message_dump

        msg = self._make_message(embed_count=1, attachment_count=1, reaction_count=1, sticker_count=1)
        result = _message_dump(msg, channel_id=1, guild_id=2)

        # should not raise
        serialized = json.dumps(result)
        assert isinstance(json.loads(serialized), dict)


# --- /debug version ---


class TestDebugVersion:
    @pytest.mark.asyncio
    async def test_version_responds_with_embed(self, mock_ctx):
        """test /debug version responds with an embed containing version info"""
        from attubot.commands.debug import debug_version

        with patch('attubot.commands.debug.os_release', return_value={'ID': 'debian', 'VERSION_ID': '12'}), patch('attubot.commands.debug.__build_time__', 'Thu Aug 11 02:23:20 UTC 2022'):
            await debug_version(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        embed = response['kwargs']['embed']
        assert embed.title == 'Version Info'
        # should have at least version, python, distro, and build time fields
        field_names = [f.name for f in embed.fields]
        assert 'Version' in field_names
        assert 'Python' in field_names
        assert 'Distro' in field_names
        assert 'Container Build Time' in field_names


# --- /test command ---


class TestTestCommand:
    @pytest.mark.asyncio
    async def test_non_owner_gets_ephemeral_rejection(self, mock_ctx_factory):
        """test that /test returns ephemeral message for non-owners"""
        from attubot.commands.debug import command_test

        ctx = mock_ctx_factory(user_id=888)

        with patch('attubot.commands.debug.config.is_owner', return_value=False):
            await command_test(ctx)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'Do I know you?' in response['args'][0]


# --- /debug force_error ---


class TestDebugForceError:
    @pytest.mark.asyncio
    async def test_force_error_raises(self, mock_ctx_factory):
        """test that /debug force_error responds then raises an exception"""
        from attubot.commands.debug import debug_force_error

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        with pytest.raises(Exception, match='Forced error'):
            await debug_force_error(ctx)

        # should have responded with the giphy link before raising
        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert 'giphy' in response


# --- /debug scheduler ---


class TestDebugScheduler:
    @pytest.mark.asyncio
    async def test_scheduler_lists_tasks(self, mock_ctx):
        """test /debug scheduler responds with an embed listing running tasks"""
        from attubot.commands.debug import debug_scheduler

        mock_sched = MagicMock()
        mock_sched.running_tasks = ['TaskLoop[NovaYearTask]', 'TaskLoop[PresenceUpdateTask]']
        mock_sched.count = 2

        with patch('attubot.commands.debug.scheduler', mock_sched):
            await debug_scheduler(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        embed = response['kwargs']['embed']
        assert embed.title == 'Tasks'
        assert 'NovaYearTask' in embed.description
        assert 'PresenceUpdateTask' in embed.description
        assert embed.fields[0].value == '2'


# --- /debug year_stats ---


class TestDebugYearStats:
    @pytest.mark.asyncio
    async def test_year_stats_responds_with_embed(self, mock_ctx, make_guild):
        """test /debug year_stats responds with an embed containing year info"""
        from attubot.client.calendar import AttuYearSpan
        from attubot.commands.debug import debug_year_stats

        make_guild()

        mock_span = AttuYearSpan(start_time=1704067200, end_time=1705276800, duration=14)

        with patch('attubot.commands.debug.get_year_status', return_value=(7, 2)), patch('attubot.commands.debug.get_year_span', new_callable=AsyncMock, return_value=mock_span):
            await debug_year_stats(mock_ctx)

        mock_ctx.respond.assert_called_once()
        response = mock_ctx._responses[0]
        embed = response['kwargs']['embed']
        assert embed.title == 'Year Stats'

        field_names = [f.name for f in embed.fields]
        assert 'Current Year' in field_names
        assert 'Time Since Epoch' in field_names
        assert 'Attu Epoch' in field_names
        assert 'Year Span' in field_names


# --- /debug message_stats ---


class TestDebugMessageStats:
    @pytest.mark.asyncio
    async def test_message_stats_guild_total(self, mock_ctx_factory):
        """test /debug message_stats without channel shows guild total"""
        from attubot.commands.debug import debug_message_stats

        ctx = mock_ctx_factory(user_id=999, is_owner=True)
        mock_repo = AsyncMock()
        mock_repo.count_for_guild = AsyncMock(return_value=12345)

        with patch('attubot.client.messages._get_repo', return_value=mock_repo):
            await debug_message_stats(ctx, channel=None)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert '12,345' in response
        assert 'guild' in response

    @pytest.mark.asyncio
    async def test_message_stats_specific_channel(self, mock_ctx_factory):
        """test /debug message_stats with channel shows channel count"""
        from attubot.commands.debug import debug_message_stats

        ctx = mock_ctx_factory(user_id=999, is_owner=True)
        mock_repo = AsyncMock()
        mock_repo.count_for_channel = AsyncMock(return_value=42)

        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 5555

        with patch('attubot.client.messages._get_repo', return_value=mock_repo):
            await debug_message_stats(ctx, channel=mock_channel)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert '42' in response

    @pytest.mark.asyncio
    async def test_message_stats_repo_not_initialized(self, mock_ctx_factory):
        """test /debug message_stats when repo is not yet initialized"""
        from attubot.commands.debug import debug_message_stats

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        with patch('attubot.client.messages._get_repo', side_effect=RuntimeError('message repo not initialized')):
            await debug_message_stats(ctx, channel=None)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'not initialized' in response['args'][0]


# --- /debug message ---


class TestDebugMessage:
    @pytest.mark.asyncio
    async def test_invalid_url_rejected(self, mock_ctx_factory):
        """test /debug message with a non-discord url gets rejected"""
        from attubot.commands.debug import debug_message

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        await debug_message(ctx, link='https://example.com/not/a/message')

        ctx.respond.assert_called_once()
        response = ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'not a valid' in response['args'][0]

    @pytest.mark.asyncio
    async def test_valid_url_message_found(self, mock_ctx_factory):
        """test /debug message with a valid url returns embed and json attachment"""
        from attubot.commands.debug import debug_message

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        # build a mock message returned from channel.history
        mock_msg = MagicMock(spec=discord.Message)
        mock_msg.id = 444555666
        mock_msg.content = 'test content'
        mock_msg.created_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)
        mock_msg.edited_at = None
        mock_msg.pinned = False
        mock_msg.jump_url = 'https://discord.com/channels/111/222/444555666'
        mock_msg.author = MagicMock()
        mock_msg.author.id = 42
        mock_msg.author.__str__ = lambda self: 'TestUser'
        mock_msg.author.display_avatar = MagicMock()
        mock_msg.author.display_avatar.url = 'https://cdn.example.com/avatar.png'
        mock_msg.embeds = []
        mock_msg.attachments = []
        mock_msg.reactions = []
        mock_msg.stickers = []

        # set up the channel.history async iterator to yield our mock message
        mock_channel = MagicMock(spec=discord.TextChannel)

        async def mock_history(**kwargs):
            yield mock_msg

        mock_channel.history = mock_history

        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=mock_channel)
        ctx.bot.get_guild = MagicMock(return_value=mock_guild)

        link = 'https://discord.com/channels/111/222/444555666'
        await debug_message(ctx, link=link)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]
        embed = response['kwargs']['embed']
        assert 'Message 444555666' in embed.title
        # should include a json file attachment
        assert 'file' in response['kwargs']

    @pytest.mark.asyncio
    async def test_message_not_found(self, mock_ctx_factory):
        """test /debug message when the target message is not in channel history"""
        from attubot.commands.debug import debug_message

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        # channel.history yields messages that don't match the target id
        mock_channel = MagicMock(spec=discord.TextChannel)

        async def mock_history(**kwargs):
            other = MagicMock(spec=discord.Message)
            other.id = 999999  # different from target
            yield other

        mock_channel.history = mock_history

        mock_guild = MagicMock()
        mock_guild.get_channel_or_thread = MagicMock(return_value=mock_channel)
        ctx.bot.get_guild = MagicMock(return_value=mock_guild)

        link = 'https://discord.com/channels/111/222/444555666'
        await debug_message(ctx, link=link)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert 'find message' in response.lower() or "couldn't find" in response.lower()

    @pytest.mark.asyncio
    async def test_message_exception_handled(self, mock_ctx_factory):
        """test /debug message handles exceptions gracefully"""
        from attubot.commands.debug import debug_message

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        # make get_guild raise an exception
        ctx.bot.get_guild = MagicMock(side_effect=AttributeError('guild not found'))

        link = 'https://discord.com/channels/111/222/444555666'
        with patch('attubot.commands.debug.logger'):
            await debug_message(ctx, link=link)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert 'could not locate' in response


# --- /debug dump_config ---


class TestDebugDumpConfig:
    @pytest.mark.asyncio
    async def test_dump_config_responds_done(self, mock_ctx_factory):
        """test /debug dump_config logs the config and responds with 'Done!'"""
        from attubot.commands.debug import debug_dump_config

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        mock_config_dict = {'database': {'url': 'mongodb://localhost'}}
        with patch('attubot.commands.debug.config.to_dict', return_value=mock_config_dict), patch('attubot.commands.debug.logger'):
            await debug_dump_config(ctx)

        ctx.respond.assert_called_once()
        response = ctx._responses[0]['args'][0]
        assert 'Done!' in response


# --- /debug dump_starboard ---


class TestDebugDumpStarboard:
    @pytest.mark.asyncio
    async def test_dump_starboard_with_messages(self, mock_ctx_factory):
        """test /debug dump_starboard with messages from the starboard bot"""
        from attubot.commands.debug import _STARBOARD_BOT_ID, debug_dump_starboard

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        # build mock messages — some from the starboard bot, some not
        starboard_msg = MagicMock(spec=discord.Message)
        starboard_msg.id = 100
        starboard_msg.author = MagicMock()
        starboard_msg.author.id = _STARBOARD_BOT_ID
        starboard_msg.created_at = datetime(2024, 3, 1, tzinfo=UTC)
        starboard_msg.content = 'star content'
        starboard_msg.embeds = []
        starboard_msg.attachments = []

        other_msg = MagicMock(spec=discord.Message)
        other_msg.id = 200
        other_msg.author = MagicMock()
        other_msg.author.id = 12345  # not the starboard bot

        mock_channel = MagicMock(spec=discord.TextChannel)

        async def mock_history(**kwargs):
            yield starboard_msg
            yield other_msg

        mock_channel.history = mock_history
        ctx.bot.get_channel = MagicMock(return_value=mock_channel)

        await debug_dump_starboard(ctx)

        # should have deferred, then responded with file
        ctx.defer.assert_called_once()
        assert len(ctx._responses) == 1
        response = ctx._responses[0]
        assert 'found 1 total' in response['args'][0]
        assert 'file' in response['kwargs']

    @pytest.mark.asyncio
    async def test_dump_starboard_empty(self, mock_ctx_factory):
        """test /debug dump_starboard when no starboard bot messages found"""
        from attubot.commands.debug import debug_dump_starboard

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        mock_channel = MagicMock(spec=discord.TextChannel)

        async def mock_history(**kwargs):
            return
            yield  # unreachable yield required to create an empty async generator

        mock_channel.history = mock_history
        ctx.bot.get_channel = MagicMock(return_value=mock_channel)

        await debug_dump_starboard(ctx)

        ctx.defer.assert_called_once()
        assert len(ctx._responses) == 1
        response = ctx._responses[0]
        assert 'found 0 total' in response['args'][0]

    @pytest.mark.asyncio
    async def test_dump_starboard_channel_not_found(self, mock_ctx_factory):
        """test /debug dump_starboard when the channel can't be found"""
        from attubot.commands.debug import debug_dump_starboard

        ctx = mock_ctx_factory(user_id=999, is_owner=True)
        ctx.bot.get_channel = MagicMock(return_value=None)

        await debug_dump_starboard(ctx)

        ctx.defer.assert_called_once()
        assert len(ctx._responses) == 1
        response = ctx._responses[0]
        assert response['kwargs'].get('ephemeral') is True
        assert 'could not find' in response['args'][0].lower()


# --- /debug progress_bar ---


class TestDebugProgressBar:
    @pytest.mark.asyncio
    async def test_progress_bar_renders_all_steps(self, mock_ctx_factory):
        """test /debug progress_bar posts initial message then edits through all steps"""
        from attubot.commands.debug import debug_progress_bar

        ctx = mock_ctx_factory(user_id=999, is_owner=True)

        mock_sent_msg = MagicMock()
        mock_sent_msg.edit = AsyncMock()
        ctx.channel.send = AsyncMock(return_value=mock_sent_msg)

        with patch('attubot.eggs.emojis.render_progress_bar', return_value='[====]'), patch('asyncio.sleep', new_callable=AsyncMock):
            await debug_progress_bar(ctx)

        # initial send + 9 edits (steps 2-10)
        ctx.channel.send.assert_called_once()
        assert mock_sent_msg.edit.call_count == 9

        # should respond ephemerally that the preview started
        ctx.respond.assert_called_once()
        response = ctx._responses[0]
        assert 'preview started' in response['args'][0]
