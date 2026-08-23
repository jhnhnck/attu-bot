# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_commands_fix_reconcile | tests for fix reconcile command and job."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from nova_core.commands.fix import fix_reconcile, job_reconcile_guild
from tests.conftest import test_guild


class TestReconcileComponents:
    @pytest.mark.asyncio
    async def test_reconcile_recent_channel_deletes_missing_and_replays_messages(self):
        from nova_core.tasks.message_backfill import MessageBackfillTask

        task = MessageBackfillTask()
        repo = MagicMock()
        repo.get_message_ids_in_window = AsyncMock(return_value=[1, 2, 3])
        repo.mark_bulk_deleted = AsyncMock()
        task._reconcile_message = AsyncMock(return_value=True)

        class FakeMessage:
            def __init__(self, _id):
                self.id = _id
                self.channel = MagicMock(id=test_guild)

        fake_msgs = [FakeMessage(1), FakeMessage(2)]

        fake_channel = MagicMock()

        async def history(**kwargs):
            for msg in fake_msgs:
                yield msg

        fake_channel.history = history

        with patch('nova_core.tasks.message_backfill._get_repo', return_value=repo):
            await task._reconcile_recent_channel(test_guild, fake_channel, lookback=timedelta(days=1))

        assert repo.mark_bulk_deleted.call_args[0][0] == [3]
        assert task._reconcile_message.await_count == len(fake_msgs)

    @pytest.mark.asyncio
    async def test_job_reconcile_handles_none_backfill_count(self, mock_ctx_factory, make_guild):
        status = MagicMock()

        make_guild(guild_id=test_guild)
        with (
            patch('nova_core.commands.fix.MessageBackfillTask._collect_channels', new_callable=AsyncMock, return_value=[MagicMock()]),
            patch('nova_core.commands.fix.job_backfill_channel', new_callable=AsyncMock, return_value=(None, 0)),
            patch('nova_core.commands.fix._safe_edit', new_callable=AsyncMock, return_value=status) as mock_edit,
            patch('nova_core.commands.fix.bot.get_guild', return_value=MagicMock(me=MagicMock())),
        ):
            await job_reconcile_guild(test_guild, status_msg=status)

        final_call = mock_edit.call_args_list[-1][0]
        assert 'Reconcile complete: 0 backfilled' in final_call[1]


@pytest.mark.asyncio
async def test_fix_reconcile_requires_repo(mock_ctx_factory):
    """fix_reconcile replies with an error when the message repo is unavailable"""
    ctx = mock_ctx_factory()

    with patch('nova_core.commands.fix.messages._get_repo', side_effect=RuntimeError('no repo')):
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
    with patch('nova_core.client.messages._get_repo', return_value=MagicMock()), patch('nova_core.commands.fix.job_reconcile_guild', new_callable=AsyncMock) as mock_job, patch('nova_core.commands.fix.scheduler.add_job') as mock_sched:
        await fix_reconcile(ctx)

    mock_sched.assert_called_once()
    args, _ = mock_sched.call_args
    assert args[1] == 'Job'
    assert args[2] == 'fix_reconcile'
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
        patch('nova_core.commands.fix.bot.get_guild', return_value=fake_guild),
        patch('nova_core.commands.fix.MessageBackfillTask._collect_channels', new_callable=AsyncMock, return_value=fake_channels) as mock_collect,
        patch('nova_core.commands.fix.job_backfill_channel', new_callable=AsyncMock, return_value=(1, 2)) as mock_backfill,
        patch('nova_core.commands.fix._safe_edit', new_callable=AsyncMock, return_value=status) as mock_edit,
    ):
        await job_reconcile_guild(test_guild, status_msg=status)
    mock_collect.assert_called_once()
    assert mock_backfill.call_count == len(fake_channels)
    assert any('Reconcile complete' in c[0][1] for c in mock_edit.call_args_list)
