"""
AttuBot - Tests for message tracking
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.database.models import MessageAuthor, MessageContent, MessageDocument, MessageRefs


test_guild = 1234567890
test_user = 9876543210
test_channel = 5555555555
test_logs = 1111111111
test_message = 2222222222


def _make_msg_doc(**kwargs) -> MessageDocument:
    """Build a MessageDocument from flat-style kwargs (matching the old field names) for testing convenience."""
    return MessageDocument(
        message_id=kwargs.pop('message_id', test_message),
        guild_id=kwargs.pop('guild_id', test_guild),
        channel_id=kwargs.pop('channel_id', test_channel),
        parent_channel_id=kwargs.pop('parent_channel_id', None),
        author=MessageAuthor(
            id=kwargs.pop('author_id', test_user),
            name=kwargs.pop('author_name', 'TestUser'),
            bot=kwargs.pop('author_bot', False),
        ),
        content=MessageContent(
            text=kwargs.pop('content', ''),
            attachments=kwargs.pop('attachments', []),
            embeds=kwargs.pop('embeds', []),
            sticker_ids=kwargs.pop('sticker_ids', []),
        ),
        refs=MessageRefs(
            reply_to=kwargs.pop('reference_id', None),
            starboard_post=kwargs.pop('starboard_reference_id', None),
        ),
        **kwargs,
    )


# --- Fixtures ---


@pytest.fixture
def message_repo():
    """MessageRepository backed by a mock async MongoDB collection."""
    from attubot.database.repositories import MessageRepository

    mock_db = MagicMock()
    return MessageRepository(mock_db)


@pytest.fixture
def mock_message_repo():
    """Patch attubot.messages._get_repo and attubot.commands.fix.messages._get_repo to return an AsyncMock repo."""
    repo = AsyncMock()
    with patch('attubot.client.messages._get_repo', return_value=repo), patch('attubot.commands.fix.messages._get_repo', return_value=repo):
        yield repo


@pytest.fixture
def guild_with_logs(make_guild):
    """Guild config with logs channel set."""
    return make_guild(guild_id=test_guild, logs_channel=test_logs)


def _make_mock_message(
    guild_id=test_guild,
    channel_id=test_channel,
    message_id=test_message,
    author_id=test_user,
    content='hello world',
    bot=False,
    public=True,
    lore_channel=False,
):
    """Build a minimal mock discord.Message."""
    msg = MagicMock()
    msg.id = message_id
    msg.content = content
    msg.guild = MagicMock()
    msg.guild.id = guild_id
    msg.guild.default_role = MagicMock()
    msg.channel = MagicMock()
    msg.channel.id = channel_id
    msg.channel.permissions_for = MagicMock(return_value=MagicMock(read_messages=public))
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.author.global_name = 'TestUser'
    msg.author.name = 'testuser'
    msg.author.bot = bot
    msg.attachments = []
    msg.embeds = []
    msg.stickers = []
    msg.snapshots = []
    msg.reference = None
    msg.pinned = False
    msg.created_at = datetime(2024, 1, 1, tzinfo=UTC)
    msg.edited_at = None
    return msg


def _make_raw_edit_payload(
    guild_id: int | None = test_guild,
    channel_id: int = test_channel,
    message_id: int = test_message,
    new_content: str = 'edited content',
    edited_timestamp: str | None = '2024-01-01T12:00:00.000000+00:00',
):
    payload = MagicMock()
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.data = {'content': new_content, 'edited_timestamp': edited_timestamp}
    payload.cached_message = None
    return payload


def _make_raw_delete_payload(
    guild_id: int | None = test_guild,
    channel_id: int = test_channel,
    message_id: int = test_message,
):
    payload = MagicMock()
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_id = message_id
    payload.cached_message = None
    return payload


def _make_raw_bulk_delete_payload(
    guild_id: int | None = test_guild,
    channel_id: int = test_channel,
    message_ids: set[int] | None = None,
):
    payload = MagicMock()
    payload.guild_id = guild_id
    payload.channel_id = channel_id
    payload.message_ids = set(message_ids or [test_message, test_message + 1])
    payload.cached_messages = []
    return payload


# --- MessageDocument model ---


class TestMessageDocument:
    def test_defaults(self):
        doc = _make_msg_doc(message_id=1, guild_id=2, channel_id=3, author_id=4, author_name='test', created_at=1000)
        assert doc.public is True
        assert doc.deleted is False
        assert doc.deleted_at is None
        assert doc.edited_at is None
        assert doc.content.attachments == []
        assert doc.content.embeds == []
        assert doc.content.sticker_ids == []
        assert doc.refs.reply_to is None
        assert doc.author.bot is False
        assert doc.content.text == ''

    def test_extra_fields_ignored(self):
        doc = _make_msg_doc(message_id=1, guild_id=2, channel_id=3, author_id=4, author_name='test', created_at=1000)
        assert doc.message_id == 1

    def test_roundtrip(self):
        doc = _make_msg_doc(
            message_id=test_message,
            guild_id=test_guild,
            channel_id=test_channel,
            author_id=test_user,
            author_name='tester',
            content='hi',
            public=False,
            created_at=1704067200,
        )
        data = doc.model_dump()
        restored = MessageDocument(**data)
        assert restored.message_id == test_message
        assert restored.public is False


# --- MessageRepository ---


class TestMessageRepository:
    async def test_init_indexes(self, message_repo):
        message_repo.db[message_repo.COLLECTION].create_index = AsyncMock()
        await message_repo.init_indexes()
        assert message_repo.db[message_repo.COLLECTION].create_index.call_count == 3

    async def test_upsert_calls_update_one(self, message_repo):
        message_repo.db[message_repo.COLLECTION].update_one = AsyncMock()
        doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='test', created_at=1000)
        await message_repo.upsert(doc)
        message_repo.db[message_repo.COLLECTION].update_one.assert_called_once()
        call_args = message_repo.db[message_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'message_id': test_message}
        assert call_args[1]['upsert'] is True

    async def test_get_found(self, message_repo):
        raw = {'message_id': test_message, 'guild_id': test_guild, 'channel_id': test_channel, 'author': {'id': test_user, 'name': 'test', 'bot': False}, 'content': {'text': '', 'attachments': [], 'embeds': [], 'sticker_ids': []}, 'refs': {'reply_to': None, 'starboard_post': None}, 'created_at': 1000, '_id': 'x'}
        message_repo.db[message_repo.COLLECTION].find_one = AsyncMock(return_value=raw)
        result = await message_repo.get(test_message)
        assert result is not None
        assert result.message_id == test_message

    async def test_get_not_found(self, message_repo):
        message_repo.db[message_repo.COLLECTION].find_one = AsyncMock(return_value=None)
        result = await message_repo.get(test_message)
        assert result is None

    async def test_mark_edited(self, message_repo):
        message_repo.db[message_repo.COLLECTION].update_one = AsyncMock()
        await message_repo.mark_edited(test_message, 'new content', 9999)
        call_args = message_repo.db[message_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'message_id': test_message}
        assert call_args[0][1]['$set']['content.text'] == 'new content'
        assert call_args[0][1]['$set']['edited_at'] == 9999

    async def test_mark_deleted(self, message_repo):
        message_repo.db[message_repo.COLLECTION].update_one = AsyncMock()
        await message_repo.mark_deleted(test_message, 9999)
        call_args = message_repo.db[message_repo.COLLECTION].update_one.call_args
        assert call_args[0][1]['$set']['deleted'] is True
        assert call_args[0][1]['$set']['deleted_at'] == 9999

    async def test_mark_bulk_deleted(self, message_repo):
        message_repo.db[message_repo.COLLECTION].update_many = AsyncMock()
        ids = [test_message, test_message + 1, test_message + 2]
        await message_repo.mark_bulk_deleted(ids, 9999)
        call_args = message_repo.db[message_repo.COLLECTION].update_many.call_args
        assert call_args[0][0] == {'message_id': {'$in': ids}}
        assert call_args[0][1]['$set']['deleted'] is True

    async def test_get_latest_in_channel_found(self, message_repo):
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[{'message_id': test_message}])
        message_repo.db[message_repo.COLLECTION].find = MagicMock(return_value=mock_cursor)
        result = await message_repo.get_latest_in_channel(test_guild, test_channel)
        assert result == test_message

    async def test_get_latest_in_channel_empty(self, message_repo):
        mock_cursor = MagicMock()
        mock_cursor.sort = MagicMock(return_value=mock_cursor)
        mock_cursor.limit = MagicMock(return_value=mock_cursor)
        mock_cursor.to_list = AsyncMock(return_value=[])
        message_repo.db[message_repo.COLLECTION].find = MagicMock(return_value=mock_cursor)
        result = await message_repo.get_latest_in_channel(test_guild, test_channel)
        assert result is None

    async def test_count_for_guild(self, message_repo):
        message_repo.db[message_repo.COLLECTION].count_documents = AsyncMock(return_value=42)
        result = await message_repo.count_for_guild(test_guild)
        assert result == 42
        message_repo.db[message_repo.COLLECTION].count_documents.assert_called_once_with({'guild_id': test_guild})

    async def test_count_for_channel(self, message_repo):
        message_repo.db[message_repo.COLLECTION].count_documents = AsyncMock(return_value=7)
        result = await message_repo.count_for_channel(test_guild, test_channel)
        assert result == 7
        message_repo.db[message_repo.COLLECTION].count_documents.assert_called_once_with({'guild_id': test_guild, 'channel_id': test_channel})

    def test_collection_name(self, message_repo):
        assert message_repo.COLLECTION == 'messages'

    async def test_distinct_author_ids(self, message_repo):
        message_repo.db[message_repo.COLLECTION].distinct = AsyncMock(return_value=[test_user, test_user + 1])
        result = await message_repo.distinct_author_ids(test_guild)
        assert result == [test_user, test_user + 1]
        message_repo.db[message_repo.COLLECTION].distinct.assert_called_once_with('author.id', {'guild_id': test_guild})

    async def test_update_author_name(self, message_repo):
        mock_result = MagicMock()
        mock_result.modified_count = 5
        message_repo.db[message_repo.COLLECTION].update_many = AsyncMock(return_value=mock_result)
        count = await message_repo.update_author_name(test_user, 'NewName')
        assert count == 5
        call_args = message_repo.db[message_repo.COLLECTION].update_many.call_args
        assert call_args[0][0] == {'author.id': test_user}
        assert call_args[0][1] == {'$set': {'author.name': 'NewName'}}


# --- store_message ---


class TestStoreMessage:
    async def test_calls_upsert(self, mock_message_repo, guild):
        from attubot.client.messages import store_message

        msg = _make_mock_message()
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            await store_message(msg)

        mock_message_repo.upsert.assert_called_once()
        doc = mock_message_repo.upsert.call_args[0][0]
        assert doc.message_id == test_message
        assert doc.guild_id == test_guild
        assert doc.channel_id == test_channel

    async def test_stores_content(self, mock_message_repo, guild):
        from attubot.client.messages import store_message

        msg = _make_mock_message(content='test content here')
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            await store_message(msg)

        doc = mock_message_repo.upsert.call_args[0][0]
        assert doc.content.text == 'test content here'

    async def test_stores_public_flag_true(self, mock_message_repo, guild):
        from attubot.client.messages import store_message

        msg = _make_mock_message(public=True)
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            await store_message(msg)

        doc = mock_message_repo.upsert.call_args[0][0]
        assert doc.public is True

    async def test_stores_public_flag_false(self, mock_message_repo, guild):
        from attubot.client.messages import store_message

        msg = _make_mock_message(public=False)
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            await store_message(msg)

        doc = mock_message_repo.upsert.call_args[0][0]
        assert doc.public is False

    async def test_swallows_repo_error(self, mock_message_repo, guild):
        from attubot.client.messages import store_message

        mock_message_repo.upsert = AsyncMock(side_effect=Exception('db gone'))
        msg = _make_mock_message()
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            # should not raise
            await store_message(msg)


# --- build_message_doc forwarded messages ---


class TestBuildMessageDocForwarded:
    async def test_no_snapshots_forwarded_false(self, mock_message_repo, guild):
        from attubot.client.messages import build_message_doc

        msg = _make_mock_message(content='normal text')
        msg.snapshots = []
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            doc = await build_message_doc(msg)

        assert doc.content.forwarded is False
        assert doc.content.text == 'normal text'

    async def test_snapshot_uses_snapshot_content(self, mock_message_repo, guild):
        from attubot.client.messages import build_message_doc

        snapshot_msg = MagicMock()
        snapshot_msg.content = 'forwarded text'
        snapshot_msg.attachments = []
        snapshot_msg.embeds = []
        snapshot_msg.stickers = []

        snapshot = MagicMock()
        snapshot.message = snapshot_msg

        msg = _make_mock_message(content='')
        msg.snapshots = [snapshot]
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            doc = await build_message_doc(msg)

        assert doc.content.forwarded is True
        assert doc.content.text == 'forwarded text'

    async def test_snapshot_message_none_falls_through(self, mock_message_repo, guild):
        from attubot.client.messages import build_message_doc

        snapshot = MagicMock()
        snapshot.message = None

        msg = _make_mock_message(content='')
        msg.snapshots = [snapshot]
        with patch('attubot.client.messages._is_archive_channel', return_value=False):
            doc = await build_message_doc(msg)

        assert doc.content.forwarded is False
        assert doc.content.text == ''


# --- log_edit ---


def _make_logs_channel():
    ch = AsyncMock()
    ch.send = AsyncMock()
    return ch


class TestLogEdit:
    async def test_sends_embed_to_logs(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='original', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_edit(payload)

        logs_ch.send.assert_called_once()
        embed = logs_ch.send.call_args[1]['embed']
        assert embed.title == 'Message Edited'

    async def test_includes_old_content(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='old text', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload(new_content='new text')

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_edit(payload)

        embed = logs_ch.send.call_args[1]['embed']
        field_names = [f.name for f in embed.fields]
        field_values = {f.name: f.value for f in embed.fields}
        assert 'Before' in field_names
        assert 'After' in field_names
        assert 'old text' in field_values['Before']
        assert 'new text' in field_values['After']

    async def test_updates_stored_record(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_edited = AsyncMock()
        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload(new_content='updated')

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_edit(payload)

        mock_message_repo.mark_edited.assert_called_once()
        args = mock_message_repo.mark_edited.call_args[0]
        assert args[0] == test_message
        assert args[1] == 'updated'

    async def test_skips_dm(self, mock_message_repo):
        from attubot.client.messages import log_edit

        payload = _make_raw_edit_payload(guild_id=None)
        with patch('attubot.client.messages._get_logs_channel', return_value=_make_logs_channel()) as mock_logs:
            await log_edit(payload)
            mock_logs.assert_not_called()

        mock_message_repo.get.assert_not_called()

    async def test_skips_if_no_logs_channel(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_edited = AsyncMock()
        payload = _make_raw_edit_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=None):
            await log_edit(payload)

        # mark_edited still gets called even if we can't log
        mock_message_repo.mark_edited.assert_called_once()

    async def test_skips_log_embed_for_bot_author(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='BotUser', content='original', created_at=1000, author_bot=True)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload(new_content='updated by bot')

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_edit(payload)

        # db record still updated
        mock_message_repo.mark_edited.assert_called_once()
        # no embed posted to logs
        logs_ch.send.assert_not_called()

    async def test_edit_embed_has_author_icon_url(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='original', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages._resolve_avatar', return_value='https://example.com/avatar.png'):
            await log_edit(payload)

        embed = logs_ch.send.call_args[1]['embed']
        assert embed.author.icon_url == 'https://example.com/avatar.png'

    async def test_edit_embed_no_icon_url_when_avatar_unavailable(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='original', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages._resolve_avatar', return_value=None):
            await log_edit(payload)

        embed = logs_ch.send.call_args[1]['embed']
        # icon_url should be empty/absent when avatar can't be resolved
        assert not embed.author.icon_url

    async def test_skips_non_edit_update_no_edited_timestamp(self, mock_message_repo, guild):
        from attubot.client.messages import log_edit

        # simulate a MESSAGE_UPDATE where discord echoes full content but edited_timestamp is null
        # (e.g. a member timeout change causes this)
        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_edited = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_edit_payload(edited_timestamp=None)

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_edit(payload)

        # nothing should be stored or logged for a non-edit update
        mock_message_repo.mark_edited.assert_not_called()
        logs_ch.send.assert_not_called()


# --- log_delete ---


class TestLogDelete:
    async def test_sends_embed_to_logs(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='deleted msg', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_delete_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_delete(payload)

        logs_ch.send.assert_called_once()
        embed = logs_ch.send.call_args[1]['embed']
        assert embed.title == 'Message Deleted'

    async def test_shows_content_from_db(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='the message', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_delete(_make_raw_delete_payload())

        embed = logs_ch.send.call_args[1]['embed']
        field_values = {f.name: f.value for f in embed.fields}
        assert 'the message' in field_values.get('Content', '')

    async def test_marks_deleted_in_db(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_deleted = AsyncMock()

        with patch('attubot.client.messages._get_logs_channel', return_value=_make_logs_channel()):
            await log_delete(_make_raw_delete_payload())

        mock_message_repo.mark_deleted.assert_called_once()
        args = mock_message_repo.mark_deleted.call_args[0]
        assert args[0] == test_message

    async def test_skips_dm(self, mock_message_repo):
        from attubot.client.messages import log_delete

        payload = _make_raw_delete_payload(guild_id=None)
        with patch('attubot.client.messages._get_logs_channel') as mock_logs:
            await log_delete(payload)
            mock_logs.assert_not_called()

    async def test_still_marks_deleted_when_no_logs_channel(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_deleted = AsyncMock()

        with patch('attubot.client.messages._get_logs_channel', return_value=None):
            await log_delete(_make_raw_delete_payload())

        mock_message_repo.mark_deleted.assert_called_once()

    async def test_delete_embed_has_author_icon_url(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(message_id=test_message, guild_id=test_guild, channel_id=test_channel, author_id=test_user, author_name='Tester', content='deleted msg', created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages._resolve_avatar', return_value='https://example.com/avatar.png'):
            await log_delete(_make_raw_delete_payload())

        embed = logs_ch.send.call_args[1]['embed']
        assert embed.author.icon_url == 'https://example.com/avatar.png'

    async def test_delete_embed_no_icon_url_without_stored_record(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages._resolve_avatar', return_value='https://example.com/avatar.png'):
            await log_delete(_make_raw_delete_payload())

        embed = logs_ch.send.call_args[1]['embed']
        # no stored record means set_author was never called - embed.author is None
        assert embed.author is None

    async def test_skips_bot_authored_message(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(author_bot=True, created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_delete(_make_raw_delete_payload())

        mock_message_repo.mark_deleted.assert_not_called()
        logs_ch.send.assert_not_called()

    async def test_skips_known_starboard_post(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete
        from attubot.database.models import StarredMessageDocument

        stored_doc = _make_msg_doc(created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        sb_doc = StarredMessageDocument(message_id=test_message, channel_id=test_channel, guild_id=test_guild, author_id=test_user, starboard_message_id=test_message + 1)
        mock_sb_repo = AsyncMock()
        mock_sb_repo.get_by_starboard_message = AsyncMock(return_value=sb_doc)

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.starboard._get_repo', return_value=mock_sb_repo):
            await log_delete(_make_raw_delete_payload())

        mock_message_repo.mark_deleted.assert_not_called()
        logs_ch.send.assert_not_called()

    async def test_skips_unknown_message_in_starboard_channel(self, mock_message_repo, make_guild):
        from attubot.client.messages import log_delete
        from attubot.config import GuildStarboard

        sb_channel = 8888888888
        gc = make_guild()
        gc.starboard = GuildStarboard(channel_id=sb_channel, emojis={})

        mock_message_repo.get = AsyncMock(return_value=None)
        mock_message_repo.mark_deleted = AsyncMock()

        logs_ch = _make_logs_channel()
        payload = _make_raw_delete_payload(channel_id=sb_channel)
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_delete(payload)

        logs_ch.send.assert_not_called()

    async def test_shows_deleted_by_when_mod_found_in_audit_log(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(author_id=test_user, created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        actor = MagicMock()
        actor.mention = f'<@{test_user + 1}>'

        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = test_user
        entry.extra = MagicMock()
        entry.extra.channel = MagicMock()
        entry.extra.channel.id = test_channel
        entry.user = actor

        async def _audit_log_iter(*args, **kwargs):
            yield entry

        mock_guild = MagicMock()
        mock_guild.audit_logs = MagicMock(return_value=_audit_log_iter())

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await log_delete(_make_raw_delete_payload())

        embed = logs_ch.send.call_args[1]['embed']
        field_names = [f.name for f in embed.fields]
        field_values = {f.name: f.value for f in embed.fields}
        assert 'Deleted by' in field_names
        assert actor.mention in field_values['Deleted by']

    async def test_no_deleted_by_when_audit_log_has_no_match(self, mock_message_repo, guild):
        from attubot.client.messages import log_delete

        stored_doc = _make_msg_doc(author_id=test_user, created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        async def _empty_audit_log(*args, **kwargs):
            return
            yield  # make it an async generator

        mock_guild = MagicMock()
        mock_guild.audit_logs = MagicMock(return_value=_empty_audit_log())

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            await log_delete(_make_raw_delete_payload())

        embed = logs_ch.send.call_args[1]['embed']
        field_names = [f.name for f in embed.fields]
        assert 'Deleted by' not in field_names

    async def test_skips_modlog_when_bot_is_actor(self, mock_message_repo, guild):
        """when the bot deleted the message, mark_deleted still runs but no modlog embed is posted"""
        from attubot.client.messages import log_delete

        bot_id = 111111111
        stored_doc = _make_msg_doc(author_id=test_user, created_at=1000)
        mock_message_repo.get = AsyncMock(return_value=stored_doc)
        mock_message_repo.mark_deleted = AsyncMock()

        bot_actor = MagicMock()
        bot_actor.id = bot_id

        entry = MagicMock()
        entry.target = MagicMock()
        entry.target.id = test_user
        entry.extra = MagicMock()
        entry.extra.channel = MagicMock()
        entry.extra.channel.id = test_channel
        entry.user = bot_actor

        async def _audit_log_iter(*args, **kwargs):
            yield entry

        mock_guild = MagicMock()
        mock_guild.audit_logs = MagicMock(return_value=_audit_log_iter())

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch), patch('attubot.client.messages.bot') as mock_bot:
            mock_bot.get_guild.return_value = mock_guild
            mock_bot.user.id = bot_id
            await log_delete(_make_raw_delete_payload())

        mock_message_repo.mark_deleted.assert_called_once()
        logs_ch.send.assert_not_called()


# --- log_bulk_delete ---


class TestLogBulkDelete:
    async def test_sends_embed_to_logs(self, mock_message_repo, guild):
        from attubot.client.messages import log_bulk_delete

        mock_message_repo.mark_bulk_deleted = AsyncMock()
        logs_ch = _make_logs_channel()
        payload = _make_raw_bulk_delete_payload()

        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_bulk_delete(payload)

        logs_ch.send.assert_called_once()
        embed = logs_ch.send.call_args[1]['embed']
        assert embed.title == 'Bulk Message Delete'

    async def test_marks_all_deleted(self, mock_message_repo, guild):
        from attubot.client.messages import log_bulk_delete

        mock_message_repo.mark_bulk_deleted = AsyncMock()
        ids = {test_message, test_message + 1, test_message + 2}
        payload = _make_raw_bulk_delete_payload(message_ids=ids)

        with patch('attubot.client.messages._get_logs_channel', return_value=_make_logs_channel()):
            await log_bulk_delete(payload)

        mock_message_repo.mark_bulk_deleted.assert_called_once()
        call_ids = mock_message_repo.mark_bulk_deleted.call_args[0][0]
        assert set(call_ids) == ids

    async def test_embed_shows_count(self, mock_message_repo, guild):
        from attubot.client.messages import log_bulk_delete

        mock_message_repo.mark_bulk_deleted = AsyncMock()
        ids = {test_message, test_message + 1}
        payload = _make_raw_bulk_delete_payload(message_ids=ids)

        logs_ch = _make_logs_channel()
        with patch('attubot.client.messages._get_logs_channel', return_value=logs_ch):
            await log_bulk_delete(payload)

        embed = logs_ch.send.call_args[1]['embed']
        field_values = {f.name: f.value for f in embed.fields}
        assert field_values.get('Count') == '2'

    async def test_skips_dm(self, mock_message_repo):
        from attubot.client.messages import log_bulk_delete

        mock_message_repo.mark_bulk_deleted = AsyncMock()
        payload = _make_raw_bulk_delete_payload(guild_id=None)

        with patch('attubot.client.messages._get_logs_channel') as mock_logs:
            await log_bulk_delete(payload)
            mock_logs.assert_not_called()

        mock_message_repo.mark_bulk_deleted.assert_not_called()


# --- on_message event ---


class TestOnMessage:
    async def test_stores_message_for_valid_guild(self, mock_message_repo, guild):
        from attubot.client.events import on_message

        msg = _make_mock_message()
        with patch('attubot.client.messages.store_message', new=AsyncMock()) as mock_store, patch('attubot.client.messages._is_archive_channel', return_value=False):
            await on_message(msg)
            mock_store.assert_called_once_with(msg)

    async def test_skips_dm(self, mock_message_repo, guild):
        from attubot.client.events import on_message

        msg = _make_mock_message()
        msg.guild = None

        with patch('attubot.client.messages.store_message', new=AsyncMock()) as mock_store:
            await on_message(msg)
            mock_store.assert_not_called()

    async def test_skips_invalid_guild(self, mock_message_repo):
        from attubot import config
        from attubot.client.events import on_message

        msg = _make_mock_message(guild_id=9999999)
        # ensure guild is NOT in valid_guilds
        assert 9999999 not in config.valid_guilds

        with patch('attubot.client.messages.store_message', new=AsyncMock()) as mock_store:
            await on_message(msg)
            mock_store.assert_not_called()

    async def test_skips_logs_channel(self, mock_message_repo, make_guild):
        from attubot.client.events import on_message
        from attubot.config import GuildChannels

        gc = make_guild()
        gc.channels = GuildChannels(logs=test_logs)

        msg = _make_mock_message(channel_id=test_logs)

        with patch('attubot.client.messages.store_message', new=AsyncMock()) as mock_store:
            await on_message(msg)
            mock_store.assert_not_called()


# --- on_raw_message_edit event ---


class TestOnRawMessageEdit:
    async def test_calls_log_edit_for_valid_guild(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_message_edit

        payload = _make_raw_edit_payload()

        with patch('attubot.client.messages.log_edit', new=AsyncMock()) as mock_log:
            await on_raw_message_edit(payload)
            mock_log.assert_called_once_with(payload)

    async def test_skips_dm(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_message_edit

        payload = _make_raw_edit_payload(guild_id=None)

        with patch('attubot.client.messages.log_edit', new=AsyncMock()) as mock_log:
            await on_raw_message_edit(payload)
            mock_log.assert_not_called()

    async def test_skips_invalid_guild(self, mock_message_repo):
        from attubot.client.events import on_raw_message_edit

        payload = _make_raw_edit_payload(guild_id=9999999)

        with patch('attubot.client.messages.log_edit', new=AsyncMock()) as mock_log:
            await on_raw_message_edit(payload)
            mock_log.assert_not_called()

    async def test_skips_logs_channel(self, mock_message_repo, make_guild):
        from attubot.client.events import on_raw_message_edit
        from attubot.config import GuildChannels

        gc = make_guild()
        gc.channels = GuildChannels(logs=test_logs)

        payload = _make_raw_edit_payload(channel_id=test_logs)

        with patch('attubot.client.messages.log_edit', new=AsyncMock()) as mock_log:
            await on_raw_message_edit(payload)
            mock_log.assert_not_called()


# --- on_raw_message_delete event ---


class TestOnRawMessageDelete:
    async def test_calls_log_delete_for_valid_guild(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_message_delete

        payload = _make_raw_delete_payload()

        with patch('attubot.client.messages.log_delete', new=AsyncMock()) as mock_log:
            await on_raw_message_delete(payload)
            mock_log.assert_called_once_with(payload)

    async def test_skips_dm(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_message_delete

        payload = _make_raw_delete_payload(guild_id=None)

        with patch('attubot.client.messages.log_delete', new=AsyncMock()) as mock_log:
            await on_raw_message_delete(payload)
            mock_log.assert_not_called()

    async def test_skips_invalid_guild(self, mock_message_repo):
        from attubot.client.events import on_raw_message_delete

        payload = _make_raw_delete_payload(guild_id=9999999)

        with patch('attubot.client.messages.log_delete', new=AsyncMock()) as mock_log:
            await on_raw_message_delete(payload)
            mock_log.assert_not_called()

    async def test_skips_logs_channel(self, mock_message_repo, make_guild):
        from attubot.client.events import on_raw_message_delete
        from attubot.config import GuildChannels

        gc = make_guild()
        gc.channels = GuildChannels(logs=test_logs)

        payload = _make_raw_delete_payload(channel_id=test_logs)

        with patch('attubot.client.messages.log_delete', new=AsyncMock()) as mock_log:
            await on_raw_message_delete(payload)
            mock_log.assert_not_called()


# --- on_raw_bulk_message_delete event ---


class TestOnRawBulkMessageDelete:
    async def test_calls_log_bulk_delete_for_valid_guild(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_bulk_message_delete

        payload = _make_raw_bulk_delete_payload()

        with patch('attubot.client.messages.log_bulk_delete', new=AsyncMock()) as mock_log:
            await on_raw_bulk_message_delete(payload)
            mock_log.assert_called_once_with(payload)

    async def test_skips_dm(self, mock_message_repo, guild):
        from attubot.client.events import on_raw_bulk_message_delete

        payload = _make_raw_bulk_delete_payload(guild_id=None)

        with patch('attubot.client.messages.log_bulk_delete', new=AsyncMock()) as mock_log:
            await on_raw_bulk_message_delete(payload)
            mock_log.assert_not_called()

    async def test_skips_invalid_guild(self, mock_message_repo):
        from attubot.client.events import on_raw_bulk_message_delete

        payload = _make_raw_bulk_delete_payload(guild_id=9999999)

        with patch('attubot.client.messages.log_bulk_delete', new=AsyncMock()) as mock_log:
            await on_raw_bulk_message_delete(payload)
            mock_log.assert_not_called()

    async def test_skips_logs_channel(self, mock_message_repo, make_guild):
        from attubot.client.events import on_raw_bulk_message_delete
        from attubot.config import GuildChannels

        gc = make_guild()
        gc.channels = GuildChannels(logs=test_logs)

        payload = _make_raw_bulk_delete_payload(channel_id=test_logs)

        with patch('attubot.client.messages.log_bulk_delete', new=AsyncMock()) as mock_log:
            await on_raw_bulk_message_delete(payload)
            mock_log.assert_not_called()


# --- job_fix_author_names ---


def _make_mock_user(global_name: str | None = 'GlobalName', name: str = 'username') -> MagicMock:
    user = MagicMock()
    user.global_name = global_name
    user.name = name
    return user


class TestJobFixAuthorNames:
    async def test_updates_all_users(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        mock_message_repo.distinct_author_ids = AsyncMock(return_value=[test_user])
        mock_message_repo.update_author_name = AsyncMock(return_value=3)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(return_value=_make_mock_user('GlobalName'))
            await job_fix_author_names(test_guild)

        mock_message_repo.update_author_name.assert_called_once_with(test_user, 'username')

    async def test_falls_back_to_name_when_no_global_name(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        mock_message_repo.distinct_author_ids = AsyncMock(return_value=[test_user])
        mock_message_repo.update_author_name = AsyncMock(return_value=1)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(return_value=_make_mock_user(global_name=None, name='rawname'))
            await job_fix_author_names(test_guild)

        mock_message_repo.update_author_name.assert_called_once_with(test_user, 'rawname')

    async def test_single_user_skips_distinct(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        mock_message_repo.update_author_name = AsyncMock(return_value=2)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(return_value=_make_mock_user())
            await job_fix_author_names(test_guild, user_id=test_user)

        mock_message_repo.distinct_author_ids.assert_not_called()
        mock_message_repo.update_author_name.assert_called_once_with(test_user, 'username')

    async def test_user_not_found_is_skipped(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        mock_message_repo.distinct_author_ids = AsyncMock(return_value=[test_user])
        mock_message_repo.update_author_name = AsyncMock(return_value=0)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(return_value=None)
            await job_fix_author_names(test_guild)

        mock_message_repo.update_author_name.assert_not_called()

    async def test_fetch_error_is_swallowed(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        mock_message_repo.distinct_author_ids = AsyncMock(return_value=[test_user])
        mock_message_repo.update_author_name = AsyncMock(return_value=0)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(side_effect=Exception('api error'))
            # should not raise
            await job_fix_author_names(test_guild)

        mock_message_repo.update_author_name.assert_not_called()

    async def test_posts_progress_to_status_msg(self, mock_message_repo, guild):
        from attubot.commands.fix import job_fix_author_names

        # build a list of 50 users to trigger the progress update at i=49
        author_ids = list(range(test_user, test_user + 50))
        mock_message_repo.distinct_author_ids = AsyncMock(return_value=author_ids)
        mock_message_repo.update_author_name = AsyncMock(return_value=1)

        status_msg = AsyncMock()
        status_msg.edit = AsyncMock(return_value=status_msg)

        with patch('attubot.bot') as mock_bot:
            mock_bot.get_or_fetch = AsyncMock(return_value=_make_mock_user())
            await job_fix_author_names(test_guild, status_msg=status_msg)

        # edit is called once at the 50-user mark, then once more for the final summary
        assert status_msg.edit.call_count >= 2
