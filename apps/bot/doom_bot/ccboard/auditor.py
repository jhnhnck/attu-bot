# SPDX-License-Identifier: Apache-2.0
"""doom_bot.ccboard.auditor | discovery / reconciliation / orphan-cleanup task.

phase 2.0 walking-skeleton stub. registers a BaseTask in the scheduler so that
/fix ccboard recover and /fix ccboard recount have a real method to dispatch
into; the methods themselves are no-ops that log and return a structured
result. real implementations land in phases 2.2 (per-entry reconcile),
2.3 (per-entry recount with re-snapshot), 2.4 (scoped discovery), and 2.5
(orphan cleanup).

design notes from the phase 2 pre-mortem (notes/plans/ccboard.md):
  * every mutating pass takes ccboard.get_lock(message_id) just like the
    watcher and manager
  * any bot-initiated reaction removal goes through the watcher's
    _safe_remove_reaction helper so _pending_bot_removals echo-suppression
    keeps working
  * recount semantic for ReactionDocument.point_value is undecided
    until phase 2.1; do not write any re-snapshot path here
  * dry_run=True is the default for any pass that mutates discord state
"""

from dataclasses import dataclass, field
from datetime import timedelta

from doom_bot.client.core import config
from doom_bot.logging import get_logger
from doom_bot.tasks.base import BaseTask


logger = get_logger(__name__)


@dataclass
class PassResult:
    """structured result for a single auditor pass invocation.

    callers (slash commands, future scheduled invocations) inspect `mutated`
    and `summary` to format a user-facing response. `details` carries
    per-pass extra fields (e.g. counters, sample ids) once real work lands.
    """

    kind: str
    dry_run: bool
    mutated: bool = False
    summary: str = 'stub'
    details: dict = field(default_factory=dict)


class AuditorTask(BaseTask):
    """auditor for ccboard drift between live discord state and the database.

    registered in the scheduler with `interval=None` so it never fires on a
    timer; today every pass is invoked from a slash command. when phase 2.4
    introduces a periodic discovery sweep, that path will set its own
    interval-style schedule (most likely a separate task class).
    """

    name: str = 'CCBoardAuditor'
    interval: timedelta | None = None
    run_immediately: bool = False

    async def on_start(self) -> None:
        await config.wait_for_ready()

    async def run(self) -> None:
        # interval is None and run_immediately is False; the scheduler should not
        # call run() at all today. log and return so a misconfiguration is
        # visible rather than silent.
        logger.debug('ccboard auditor: run() called with no schedule; this is a stub')

    async def reconcile_entry(self, guild_id: int, message_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.2 placeholder: reconcile one entry against live discord.

        the real implementation diffs `ccboard_reactions` against the message's
        current discord reactions, soft-deletes phantom records, and adds
        missing ones. dry_run=True (the default) reports the diff without
        mutating anything.
        """
        logger.info(f'ccboard auditor: reconcile_entry stub for guild={guild_id} message={message_id} dry_run={dry_run}')
        return PassResult(
            kind='reconcile_entry',
            dry_run=dry_run,
            summary=f'stub: per-entry reconcile is phase 2.2; would have run on message {message_id}',
        )

    async def reconcile_guild(self, guild_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.2 placeholder: reconcile every entry in a guild.

        guild-scope wrapper around `reconcile_entry`. real implementation
        iterates `ccboard_entries`, takes per-entry locks, and aggregates
        diffs into a summary.
        """
        logger.info(f'ccboard auditor: reconcile_guild stub for guild={guild_id} dry_run={dry_run}')
        return PassResult(
            kind='reconcile_guild',
            dry_run=dry_run,
            summary=f'stub: guild-wide reconcile is phase 2.2; would have run on guild {guild_id}',
        )

    async def recount_entry(self, guild_id: int, message_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.3 placeholder: re-snapshot point_value for one entry.

        cannot be implemented before phase 2.1 pins the recount semantic
        (rename point_value, add last_recounted_at, or accept silent drift).
        """
        logger.info(f'ccboard auditor: recount_entry stub for guild={guild_id} message={message_id} dry_run={dry_run}')
        return PassResult(
            kind='recount_entry',
            dry_run=dry_run,
            summary='stub: per-entry recount is phase 2.3; awaits phase 2.1 design decision',
        )

    async def discover_guild(self, guild_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.4 placeholder: scan recently-active channels for missed reactions.

        real implementation scopes the scan to channels with recent ccboard
        reactions (per the phase 2 pre-mortem, an unbounded channel scan was
        flagged as a high-severity performance risk).
        """
        logger.info(f'ccboard auditor: discover_guild stub for guild={guild_id} dry_run={dry_run}')
        return PassResult(
            kind='discover_guild',
            dry_run=dry_run,
            summary=f'stub: scoped discovery is phase 2.4; would have run on guild {guild_id}',
        )

    async def cleanup_orphans(self, guild_id: int, *, dry_run: bool = True, grace_days: int = 7) -> PassResult:
        """phase 2.5 placeholder: delete bot-authored ccboard posts with no DB twin.

        real implementation respects `grace_days` so freshly-created posts
        whose entry write failed are not deleted before the manager retries.
        """
        logger.info(f'ccboard auditor: cleanup_orphans stub for guild={guild_id} dry_run={dry_run} grace_days={grace_days}')
        return PassResult(
            kind='cleanup_orphans',
            dry_run=dry_run,
            summary=f'stub: orphan cleanup is phase 2.5; would have run on guild {guild_id} (grace {grace_days}d)',
        )


# singleton instance for registration
auditor_task = AuditorTask()


logger.info('registered: ccboard auditor')
