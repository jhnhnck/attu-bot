# SPDX-License-Identifier: Apache-2.0
"""tests.python.unit.test_ccboard_auditor | unit tests for the ccboard auditor task.

phase 2.0 walking skeleton: verifies the task wires into the scheduler and that
each pass method returns a structured PassResult without crashing. real
behavior tests land alongside the per-phase implementations (2.2 / 2.3 / 2.4 / 2.5).
"""

import pytest

from doom_bot.ccboard.auditor import AuditorTask, PassResult, auditor_task


guild_id = 1234567890
message_id = 111000111000111000


# --- Singleton ---


def test_singleton_is_audit_task():
    assert isinstance(auditor_task, AuditorTask)


def test_task_metadata_runs_manual_only():
    """interval=None and run_immediately=False keep the scheduler from firing run() on a timer.

    every pass is currently slash-command-driven; phase 2.4 will introduce a
    separately-scheduled discovery sweep, so this assertion locks in the
    walking-skeleton's "manual-only" stance.
    """
    assert auditor_task.interval is None
    assert auditor_task.run_immediately is False
    assert auditor_task.run_once is False
    assert auditor_task.name == 'CCBoardAuditor'


# --- Pass stubs ---


@pytest.mark.asyncio
async def test_run_is_a_no_op():
    """run() should not raise; today the scheduler shouldn't call it at all"""
    await auditor_task.run()


@pytest.mark.asyncio
async def test_reconcile_entry_returns_dry_run_stub():
    result = await auditor_task.reconcile_entry(guild_id, message_id)
    assert isinstance(result, PassResult)
    assert result.kind == 'reconcile_entry'
    assert result.dry_run is True
    assert result.mutated is False
    assert 'phase 2.2' in result.summary
    assert str(message_id) in result.summary


@pytest.mark.asyncio
async def test_reconcile_entry_honors_dry_run_false_passthrough():
    """callers may opt into dry_run=False; the stub still does not mutate"""
    result = await auditor_task.reconcile_entry(guild_id, message_id, dry_run=False)
    assert result.dry_run is False
    assert result.mutated is False


@pytest.mark.asyncio
async def test_reconcile_guild_returns_stub():
    result = await auditor_task.reconcile_guild(guild_id)
    assert result.kind == 'reconcile_guild'
    assert result.dry_run is True
    assert result.mutated is False
    assert str(guild_id) in result.summary


@pytest.mark.asyncio
async def test_recount_entry_advertises_phase_2_1_dependency():
    """the recount stub should call out the gating design decision in its summary"""
    result = await auditor_task.recount_entry(guild_id, message_id)
    assert result.kind == 'recount_entry'
    assert 'phase 2.1' in result.summary
    assert result.mutated is False


@pytest.mark.asyncio
async def test_discover_guild_returns_stub():
    result = await auditor_task.discover_guild(guild_id)
    assert result.kind == 'discover_guild'
    assert result.dry_run is True
    assert result.mutated is False


@pytest.mark.asyncio
async def test_cleanup_orphans_advertises_grace_period():
    result = await auditor_task.cleanup_orphans(guild_id, grace_days=14)
    assert result.kind == 'cleanup_orphans'
    assert result.dry_run is True
    assert '14d' in result.summary
    assert result.mutated is False


# --- Scheduler wiring ---


def test_register_bot_tasks_includes_auditor():
    """register_bot_tasks() must register the auditor singleton on the scheduler.

    walking-skeleton purpose: prove that the scheduler can find the task class
    so that future phases can flip it to interval-driven without rewiring.
    """
    from doom_bot.tasks import register_bot_tasks
    from doom_bot.tasks.scheduler import TaskScheduler

    scheduler = TaskScheduler()
    register_bot_tasks(scheduler)
    registered_names = {task.name for task in scheduler.registered_tasks()}
    assert 'CCBoardAuditor' in registered_names


def test_register_bot_tasks_is_idempotent_for_auditor():
    """re-registering should not duplicate the auditor in the scheduler"""
    from doom_bot.tasks import register_bot_tasks
    from doom_bot.tasks.scheduler import TaskScheduler

    scheduler = TaskScheduler()
    register_bot_tasks(scheduler)
    register_bot_tasks(scheduler)
    auditor_count = sum(1 for task in scheduler.registered_tasks() if task.name == 'CCBoardAuditor')
    assert auditor_count == 1
