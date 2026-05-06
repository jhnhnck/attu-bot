"""
AttuBot - Tests for chat/RAG database models and repositories
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import os
import time as _time


os.environ['TZ'] = 'UTC'
_time.tzset()

from unittest.mock import AsyncMock, MagicMock

import pytest

from attu_models import (
    ChatChannelConfig,
    ChatConfigDocument,
    ChatSourceDocument,
    ReloadSignalDocument,
)


# --- ChatChannelConfig ---


class TestChatChannelConfig:
    def test_requires_name(self):
        with pytest.raises(Exception):
            ChatChannelConfig()  # pyright: ignore[reportCallIssue]

    def test_defaults(self):
        cfg = ChatChannelConfig(name='lore-news')
        assert cfg.name == 'lore-news'
        assert cfg.description == ''
        assert cfg.channel_type == 'discussion'
        assert cfg.ingest is True

    def test_roleplay_type(self):
        cfg = ChatChannelConfig(name='rp-channel', channel_type='roleplay')
        assert cfg.channel_type == 'roleplay'

    def test_shitpost_type(self):
        cfg = ChatChannelConfig(name='memes', channel_type='shitpost')
        assert cfg.channel_type == 'shitpost'

    def test_extra_fields_ignored(self):
        cfg = ChatChannelConfig(name='test', unknown_field='x')  # pyright: ignore[reportCallIssue]
        assert cfg.name == 'test'


# --- ChatConfigDocument ---


class TestChatConfigDocument:
    def test_defaults(self):
        doc = ChatConfigDocument()
        assert doc.config_type == 'chat'
        assert doc.discord_lookback_hours == 6
        assert doc.discord_window_minutes == 30
        assert doc.noise_filter_min_tokens == 20
        assert doc.ignored_user_ids == []
        assert doc.ingest_discord is True
        assert doc.ingest_wiki is True
        assert doc.ingest_documents is True
        assert doc.wiki_namespaces == ['0']
        assert doc.character_log_channel_id is None
        assert doc.chat_channels == {}
        assert doc.user_nations == {}
        assert doc.retrieval_top_k_wiki == 5
        assert doc.retrieval_top_k_discord == 5
        assert doc.retrieval_top_k_documents == 3
        assert doc.retrieval_top_k_images == 2

    def test_config_type_is_literal(self):
        # config_type is fixed; if provided it must be 'chat'
        doc = ChatConfigDocument(config_type='chat')
        assert doc.config_type == 'chat'

    def test_chat_channels_parsed(self):
        doc = ChatConfigDocument(
            chat_channels={  # pyright: ignore[reportArgumentType]
                '111111': {'name': 'lore-news', 'channel_type': 'roleplay'},
                '222222': {'name': 'general', 'channel_type': 'discussion', 'ingest': False},
            }
        )
        assert '111111' in doc.chat_channels
        assert doc.chat_channels['111111'].channel_type == 'roleplay'
        assert doc.chat_channels['222222'].ingest is False

    def test_ignored_user_ids(self):
        doc = ChatConfigDocument(ignored_user_ids=[111, 222, 333])
        assert 222 in doc.ignored_user_ids

    def test_extra_fields_ignored(self):
        doc = ChatConfigDocument(unknown_field='x')  # pyright: ignore[reportCallIssue]
        assert doc.config_type == 'chat'

    def test_ingest_wiki_toggle(self):
        doc = ChatConfigDocument(ingest_wiki=False)
        assert doc.ingest_wiki is False

    def test_wiki_namespaces(self):
        doc = ChatConfigDocument(wiki_namespaces=['0', '4'])
        assert '4' in doc.wiki_namespaces

    def test_user_nations(self):
        doc = ChatConfigDocument(user_nations={'123456789': 'Faltir', '987654321': 'Kalam'})
        assert doc.user_nations['123456789'] == 'Faltir'


# --- ChatSourceDocument ---


class TestChatSourceDocument:
    def test_required_fields(self):
        doc = ChatSourceDocument(
            source_id='wiki_test_intro',
            source_type='wiki_section',
            content_hash='abc123',
            last_ingested=1700000000,
        )
        assert doc.source_id == 'wiki_test_intro'
        assert doc.source_type == 'wiki_section'
        assert doc.content_hash == 'abc123'
        assert doc.last_ingested == 1700000000

    def test_defaults(self):
        doc = ChatSourceDocument(
            source_id='x',
            source_type='wiki_section',
            content_hash='y',
            last_ingested=0,
        )
        assert doc.qdrant_point_ids == []
        assert doc.flagged_incorrect is False
        assert doc.metadata == {}

    def test_qdrant_point_ids(self):
        doc = ChatSourceDocument(
            source_id='x',
            source_type='wiki_section',
            content_hash='y',
            last_ingested=0,
            qdrant_point_ids=['uuid-1', 'uuid-2'],
        )
        assert 'uuid-1' in doc.qdrant_point_ids

    def test_flagged_incorrect(self):
        doc = ChatSourceDocument(
            source_id='x',
            source_type='wiki_section',
            content_hash='y',
            last_ingested=0,
            flagged_incorrect=True,
        )
        assert doc.flagged_incorrect is True

    def test_metadata(self):
        doc = ChatSourceDocument(
            source_id='x',
            source_type='wiki_section',
            content_hash='y',
            last_ingested=0,
            metadata={'page_title': 'Faltir', 'section': 'History'},
        )
        assert doc.metadata['page_title'] == 'Faltir'

    def test_extra_fields_ignored(self):
        doc = ChatSourceDocument(
            source_id='x',
            source_type='wiki_section',
            content_hash='y',
            last_ingested=0,
            unknown='z',  # pyright: ignore[reportCallIssue]
        )
        assert doc.source_id == 'x'


# --- ReloadSignalDocument - 'chat' type ---


class TestReloadSignalChatType:
    def test_make_chat(self):
        doc = ReloadSignalDocument.make('chat')
        assert doc.signal_type == 'chat'
        assert doc.guild_id is None
        assert doc.timestamp > 0

    def test_chat_signal_accepted(self):
        doc = ReloadSignalDocument(signal_type='chat', guild_id=None, timestamp=1000)
        assert doc.signal_type == 'chat'


# --- ChatSourceRepository ---


@pytest.fixture
def chat_source_repo():
    from attu_models import ChatSourceRepository

    mock_db = MagicMock()
    return ChatSourceRepository(mock_db)


class TestChatSourceRepository:
    async def test_init_indexes(self, chat_source_repo):
        chat_source_repo.db[chat_source_repo.COLLECTION].create_index = AsyncMock()
        await chat_source_repo.init_indexes()
        assert chat_source_repo.db[chat_source_repo.COLLECTION].create_index.call_count == 2

    async def test_get_returns_none_when_missing(self, chat_source_repo):
        chat_source_repo.db[chat_source_repo.COLLECTION].find_one = AsyncMock(return_value=None)
        result = await chat_source_repo.get('wiki_test_intro')
        assert result is None

    async def test_get_returns_document(self, chat_source_repo):
        raw = {
            '_id': 'fake_id',
            'source_id': 'wiki_test_intro',
            'source_type': 'wiki_section',
            'content_hash': 'abc123',
            'last_ingested': 1700000000,
        }
        chat_source_repo.db[chat_source_repo.COLLECTION].find_one = AsyncMock(return_value=raw)
        result = await chat_source_repo.get('wiki_test_intro')
        assert result is not None
        assert result.source_id == 'wiki_test_intro'

    async def test_upsert_uses_source_id_as_key(self, chat_source_repo):
        chat_source_repo.db[chat_source_repo.COLLECTION].update_one = AsyncMock()
        doc = ChatSourceDocument(
            source_id='wiki_test_intro',
            source_type='wiki_section',
            content_hash='abc123',
            last_ingested=1700000000,
        )
        await chat_source_repo.upsert(doc)
        call_args = chat_source_repo.db[chat_source_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'source_id': 'wiki_test_intro'}
        assert call_args[1]['upsert'] is True

    async def test_flag_incorrect(self, chat_source_repo):
        chat_source_repo.db[chat_source_repo.COLLECTION].update_one = AsyncMock()
        await chat_source_repo.flag_incorrect('wiki_test_intro')
        call_args = chat_source_repo.db[chat_source_repo.COLLECTION].update_one.call_args
        assert call_args[0][0] == {'source_id': 'wiki_test_intro'}
        assert call_args[0][1]['$set']['flagged_incorrect'] is True

    async def test_collection_name(self, chat_source_repo):
        assert chat_source_repo.COLLECTION == 'chat_sources'
