"""
AttuBot - Fix Command Reconcile Tests
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from attubot.commands.fix import fix_reconcile, job_reconcile_guild
from tests.conftest import TEST_GUILD


class TestReconcileComponents:
    @pytest.mark.asyncio
    async def test_reconcile_recent_channel_deletes_missing_and_replays_messages(self):
        from attubot.tasks.message_backfill import MessageBackfillTask

        task = MessageBackfillTask()
        repo = MagicMock()
        repo.get_message_ids_in_window = AsyncMock(return_value=[1, 2, 3])
        repo.mark_bulk_deleted = AsyncMock()
        task._reconcile_message = AsyncMock(return_value=True)

        class FakeMessage:
            def __init__(self, _id):
                self.id = _id
                self.channel = MagicMock(id=TEST_GUILD)

        fake_msgs = [FakeMessage(1), FakeMessage(2)]

        fake_channel = MagicMock()

        async def history(**kwargs):
            for msg in fake_msgs:
                yield msg

        fake_channel.history = history

        with patch('attubot.tasks.message_backfill._get_repo', return_value=repo):
            await task._reconcile_recent_channel(TEST_GUILD, fake_channel, lookback=timedelta(days=1))

        assert repo.mark_bulk_deleted.call_args[0][0] == [3]
        assert task._reconcile_message.await_count == len(fake_msgs)

    @pytest.mark.asyncio
    async def test_job_reconcile_handles_none_backfill_count(self, mock_ctx_factory, make_guild):
        status = MagicMock()

        make_guild(guild_id=TEST_GUILD)
        with (
            patch('attubot.commands.fix.MessageBackfillTask._collect_channels', new_callable=AsyncMock, return_value=[MagicMock()]),
            patch('attubot.commands.fix.job_backfill_channel', new_callable=AsyncMock, return_value=(None, 0)),
            patch('attubot.commands.fix._safe_edit', new_callable=AsyncMock, return_value=status) as mock_edit,
            patch('attubot.commands.fix.bot.get_guild', return_value=MagicMock(me=MagicMock())),
        ):
            await job_reconcile_guild(TEST_GUILD, status_msg=status)

        final_call = mock_edit.call_args_list[-1][0]
        assert 'Reconcile complete: 0 backfilled' in final_call[1]


@pytest.mark.asyncio
async def test_fix_reconcile_requires_repo(mock_ctx_factory):
    """fix_reconcile replies with an error when the message repo is unavailable"""
    ctx = mock_ctx_factory()

    with patch('attubot.commands.fix.messages._get_repo', side_effect=RuntimeError('no repo')):
        await fix_reconcile(ctx)

    assert ctx._responses
    response = ctx._responses[0]
    assert 'message repo not initialized yet' in response['args'][0]
    assert response['kwargs'].get('ephemeral') is True


@pytest.mark.asyncio
async def test_fix_reconcile_schedules_job(mock_ctx_factory):
    """fix_reconcile schedules job_reconcile_guild when the repo is ready"""
    ctx = mock_ctx_factory()

    ctx.channel.send = AsyncMock(return_value=MagicMock())
    with patch('attubot.messages._get_repo', return_value=MagicMock()), patch('attubot.commands.fix.job_reconcile_guild', new_callable=AsyncMock) as mock_job, patch('attubot.commands.fix.scheduler.add_job') as mock_sched:
        await fix_reconcile(ctx)

    mock_sched.assert_called_once()
    args, _ = mock_sched.call_args
    assert args[1] == 'Job[fix_reconcile]'
    assert mock_job.call_args[0][0] == ctx.guild.id


@pytest.mark.asyncio
async def test_job_reconcile_guild_scans_channels(make_guild):
    """job_reconcile_guild iterates readable channels and reconciles them"""
    make_guild()
    status = MagicMock()
    fake_channels = [MagicMock(id=1), MagicMock(id=2)]
    fake_guild = MagicMock()
    fake_guild.me = MagicMock()

    with (
        patch('attubot.commands.fix.bot.get_guild', return_value=fake_guild),
        patch('attubot.commands.fix.MessageBackfillTask._collect_channels', new_callable=AsyncMock, return_value=fake_channels) as mock_collect,
        patch('attubot.commands.fix.job_backfill_channel', new_callable=AsyncMock, return_value=(1, 2)) as mock_backfill,
        patch('attubot.commands.fix._safe_edit', new_callable=AsyncMock, return_value=status) as mock_edit,
    ):
        await job_reconcile_guild(TEST_GUILD, status_msg=status)

    mock_collect.assert_called_once()
    assert mock_backfill.call_count == len(fake_channels)
    assert any('Reconcile complete' in c[0][1] for c in mock_edit.call_args_list)
