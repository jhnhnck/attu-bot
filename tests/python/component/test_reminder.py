"""
AttuBot - Reminder Repository Component Tests (real MongoDB)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.

These tests run against a real MongoDB instance. Each test gets isolated
collections via the component_db fixture from conftest.py.
"""

import time

import pytest

from attubot.database.models import ReminderDocument
from attubot.database.repositories import ReminderRepository


pytestmark = pytest.mark.component

reminder_guild = 1111111111
reminder_user = 2222222222
reminder_channel = 3333333333


def _make_reminder(reminder_id: str = 'aaaaaaaa-1111-2222-3333-444444444444', **kwargs) -> ReminderDocument:
    defaults = {
        'reminder_id': reminder_id,
        'guild_id': reminder_guild,
        'user_id': reminder_user,
        'channel_id': reminder_channel,
        'attu_year': 5,
        'attu_month': None,
        'attu_day': None,
        'note': '',
        'created_at': int(time.time()),
    }
    defaults.update(kwargs)
    return ReminderDocument(**defaults)


# --- Repository CRUD ---


class TestReminderRepositoryCRUD:
    @pytest.mark.asyncio
    async def test_insert_and_get_roundtrip(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder(attu_year=5, attu_month=3, attu_day=15, note='test note')
        await repo.insert(doc)

        result = await repo.get(doc.reminder_id)
        assert result is not None
        assert result.reminder_id == doc.reminder_id
        assert result.attu_year == 5
        assert result.attu_month == 3
        assert result.attu_day == 15
        assert result.note == 'test note'
        assert result.fired is False

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, component_db):
        repo = ReminderRepository(component_db)
        result = await repo.get('nonexistent-id')
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_removes_document(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder()
        await repo.insert(doc)
        assert await repo.get(doc.reminder_id) is not None

        deleted = await repo.delete(doc.reminder_id)
        assert deleted is True
        assert await repo.get(doc.reminder_id) is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_returns_false(self, component_db):
        repo = ReminderRepository(component_db)
        result = await repo.delete('nonexistent-id')
        assert result is False

    @pytest.mark.asyncio
    async def test_update_message_id(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder()
        await repo.insert(doc)

        await repo.update_message_id(doc.reminder_id, 9999999999)
        result = await repo.get(doc.reminder_id)
        assert result is not None
        assert result.message_id == 9999999999


# --- Querying ---


class TestReminderRepositoryQueries:
    @pytest.mark.asyncio
    async def test_list_all_unfired(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        unfired = _make_reminder(reminder_id='unfired-1')
        fired = _make_reminder(reminder_id='fired-1', fired=True, fired_at=int(time.time()))
        await repo.insert(unfired)
        await repo.insert(fired)

        results = await repo.list_all_unfired()
        assert len(results) == 1
        assert results[0].reminder_id == 'unfired-1'

    @pytest.mark.asyncio
    async def test_list_active_for_user(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        # user A's reminders
        r1 = _make_reminder(reminder_id='user-a-1', user_id=1111, attu_year=5)
        r2 = _make_reminder(reminder_id='user-a-2', user_id=1111, attu_year=3)
        # user B's reminder
        r3 = _make_reminder(reminder_id='user-b-1', user_id=2222, attu_year=4)
        # user A's fired reminder
        r4 = _make_reminder(reminder_id='user-a-fired', user_id=1111, attu_year=2, fired=True, fired_at=int(time.time()))

        for doc in [r1, r2, r3, r4]:
            await repo.insert(doc)

        results = await repo.list_active_for_user(reminder_guild, 1111)
        assert len(results) == 2
        # should be sorted by attu_year ascending
        assert results[0].attu_year == 3
        assert results[1].attu_year == 5

    @pytest.mark.asyncio
    async def test_mark_fired(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder()
        await repo.insert(doc)

        now = int(time.time())
        await repo.mark_fired(doc.reminder_id, now)

        result = await repo.get(doc.reminder_id)
        assert result is not None
        assert result.fired is True
        assert result.fired_at == now

    @pytest.mark.asyncio
    async def test_get_by_prefix(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder(reminder_id='abcdefgh-1234-5678-9012-abcdefabcdef')
        await repo.insert(doc)

        result = await repo.get_by_prefix('abcdefgh', reminder_guild, reminder_user)
        assert result is not None
        assert result.reminder_id == doc.reminder_id

    @pytest.mark.asyncio
    async def test_get_by_prefix_wrong_user(self, component_db):
        repo = ReminderRepository(component_db)
        await repo.init_indexes()

        doc = _make_reminder(reminder_id='abcdefgh-1234-5678-9012-abcdefabcdef')
        await repo.insert(doc)

        result = await repo.get_by_prefix('abcdefgh', reminder_guild, 9999999999)
        assert result is None
