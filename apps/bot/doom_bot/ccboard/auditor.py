# SPDX-License-Identifier: Apache-2.0
"""doom_bot.ccboard.auditor | discovery / reconciliation / orphan-cleanup task.

phases shipped so far:
  * 2.0 walking skeleton — task registered with manual-only schedule; every
    pass returns a structured PassResult
  * 2.2 per-entry reconcile — diffs ccboard_reactions against live discord
    state; dry_run=True default; degrades to add+refresh-only when discord
    pagination is partial; uses ccboard.get_lock and the watcher's
    _safe_remove_reaction so echo-suppression keeps working

phases still stub:
  * 2.3 per-entry recount with re-snapshot (option B+ from phase 2.1:
    ReactionDocument.last_recounted_at + GuildCCBoard.weights_updated_at,
    targeted via staleness predicate)
  * 2.4 scoped discovery — channel-history scan limited to channels with
    recent ccboard reactions
  * 2.5 orphan-post cleanup with grace period

design notes from the phase 2 pre-mortem (notes/plans/ccboard.md):
  * every mutating pass takes ccboard.get_lock(message_id) just like the
    watcher and manager
  * any bot-initiated reaction removal goes through the watcher's
    _safe_remove_reaction helper so _pending_bot_removals echo-suppression
    keeps working
  * dry_run=True is the default for any pass that mutates discord state
"""

import time
from dataclasses import dataclass, field
from datetime import timedelta

import discord

from attu_models import ReactionDocument
from doom_bot import ccboard
from doom_bot.client.core import config
from doom_bot.config import UnauthorizedGuild
from doom_bot.logging import get_logger
from doom_bot.tasks.base import BaseTask


logger = get_logger(__name__)


# --- Result type ---


@dataclass
class PassResult:
    """structured result for a single auditor pass invocation.

    callers (slash commands, future scheduled invocations) inspect `mutated`
    and `summary` to format a user-facing response. `details` carries
    per-pass extra fields (counters, sample ids).
    """

    kind: str
    dry_run: bool
    mutated: bool = False
    summary: str = 'stub'
    details: dict = field(default_factory=dict)


# --- Internal helpers ---


def _credited_author_id(entry) -> int:
    return entry.effective_author_id if entry.effective_author_id is not None else entry.author_id


async def _fetch_discord_message(guild_id: int, channel_id: int, message_id: int) -> discord.Message | None:
    """fetch one discord message; return None on any expected failure mode"""
    from doom_bot.client.core import bot

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'ccboard auditor: channel {channel_id} unavailable for guild {guild_id}: {err}')
        return None
    if not isinstance(channel, discord.abc.Messageable):
        return None
    try:
        return await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'ccboard auditor: discord fetch failed for {message_id} in guild {guild_id}: {err}')
        return None


@dataclass
class _LiveReaction:
    """one user/emoji pair seen on discord during reconcile"""

    user_id: int
    emoji_str: str
    is_super: bool
    is_bot_reactor: bool


async def _collect_live_reactions(
    discord_msg: discord.Message,
    *,
    configured_emojis: set[str],
) -> tuple[list[_LiveReaction], bool]:
    """walk one message's discord reactions and collect user/emoji rows.

    returns (rows, partial). `partial` is True if any reaction.users()
    iteration failed; callers should skip the remove-side of the diff in
    partial mode to avoid wiping real votes from incomplete data.

    one-vote enforcement is NOT applied here — caller resolves it after
    deciding which rows to keep (self/bot policy, etc).
    """
    rows: list[_LiveReaction] = []
    partial = False
    for reaction in discord_msg.reactions:
        emoji = str(reaction.emoji)
        if emoji not in configured_emojis:
            continue
        is_super = bool(getattr(reaction, 'is_burst', False))
        try:
            users_iter = reaction.users()
        except Exception as err:
            logger.warn(f'ccboard auditor: reaction.users() failed for {emoji} on {discord_msg.id}: {err}; treating as partial')
            partial = True
            continue
        try:
            async for user in users_iter:
                rows.append(_LiveReaction(user_id=user.id, emoji_str=emoji, is_super=is_super, is_bot_reactor=bool(getattr(user, 'bot', False))))
        except Exception as err:
            logger.warn(f'ccboard auditor: pagination failed mid-stream for {emoji} on {discord_msg.id}: {err}; treating as partial')
            partial = True
            continue
    return rows, partial


def _resolve_one_vote(rows: list[_LiveReaction]) -> dict[int, _LiveReaction]:
    """apply one-vote-per-message: per user, keep the first emoji seen.

    matches the watcher's `_backfill_existing_reactions` policy so reconcile
    converges to the same state the watcher would produce.
    """
    seen: dict[int, _LiveReaction] = {}
    for row in rows:
        seen.setdefault(row.user_id, row)
    return seen


@dataclass
class _ReconcileDiff:
    """structured per-user diff between live discord and the database"""

    # users in live but absent from db (or in db but soft-deleted) — would create new
    to_add: list[_LiveReaction] = field(default_factory=list)
    # users in both, but the live emoji or super flag differs from the db record
    to_replace: list[tuple[_LiveReaction, ReactionDocument]] = field(default_factory=list)
    # users in db active state but missing from live — would soft-delete
    to_remove: list[ReactionDocument] = field(default_factory=list)
    # invalid live rows (bot reactor, self-reaction); would auto-remove from discord
    to_strip_from_discord: list[_LiveReaction] = field(default_factory=list)
    # users with multiple live rows; the extras would be auto-removed from discord
    to_strip_extras: list[_LiveReaction] = field(default_factory=list)
    # users in both with matching emoji+super — no change needed (counted, not enumerated)
    matching_count: int = 0


def _compute_diff(
    *,
    live_rows: list[_LiveReaction],
    db_active: dict[int, ReactionDocument],
    credited_author_id: int,
    partial: bool,
) -> _ReconcileDiff:
    """pure function: compare live discord state to db state.

    callers in dry-run mode use the diff to render a summary. callers in
    apply mode use the diff as the mutation plan. partial=True suppresses
    `to_remove` so missing-from-live records (which might be missing only
    because pagination failed) are not soft-deleted.
    """
    diff = _ReconcileDiff()

    # one-vote enforcement: first emoji seen per user wins
    primary_per_user = _resolve_one_vote(live_rows)

    # extras (multiple live rows for one user, after the first)
    primary_keys: set[tuple[int, str, bool]] = {(r.user_id, r.emoji_str, r.is_super) for r in primary_per_user.values()}
    for row in live_rows:
        if (row.user_id, row.emoji_str, row.is_super) not in primary_keys:
            diff.to_strip_extras.append(row)

    # self/bot rows in the primary set get stripped, not added
    valid_live: dict[int, _LiveReaction] = {}
    for user_id, row in primary_per_user.items():
        if row.is_bot_reactor or user_id == credited_author_id:
            diff.to_strip_from_discord.append(row)
        else:
            valid_live[user_id] = row

    # diff per user: add / replace / matching
    for user_id, live_row in valid_live.items():
        db_row = db_active.get(user_id)
        if db_row is None:
            diff.to_add.append(live_row)
            continue
        if db_row.emoji_str == live_row.emoji_str and db_row.is_super == live_row.is_super:
            diff.matching_count += 1
            continue
        diff.to_replace.append((live_row, db_row))

    # remove side — only when not partial
    if not partial:
        for user_id, db_row in db_active.items():
            if user_id not in valid_live:
                diff.to_remove.append(db_row)

    return diff


def _summarize_diff(diff: _ReconcileDiff, *, partial: bool, dry_run: bool, message_id: int) -> str:
    """compact one-line summary for the slash-command response"""
    parts = [
        f'msg={message_id}',
        f'add={len(diff.to_add)}',
        f'replace={len(diff.to_replace)}',
        f'remove={len(diff.to_remove)}',
        f'match={diff.matching_count}',
        f'strip_invalid={len(diff.to_strip_from_discord)}',
        f'strip_extras={len(diff.to_strip_extras)}',
    ]
    if partial:
        parts.append('PARTIAL(removes suppressed)')
    parts.append('dry_run' if dry_run else 'APPLIED')
    return ' '.join(parts)


def _diff_details(diff: _ReconcileDiff, *, partial: bool) -> dict:
    """structured details suitable for logs and PassResult.details"""
    return {
        'add': len(diff.to_add),
        'replace': len(diff.to_replace),
        'remove': len(diff.to_remove),
        'match': diff.matching_count,
        'strip_invalid': len(diff.to_strip_from_discord),
        'strip_extras': len(diff.to_strip_extras),
        'partial': partial,
    }


# --- Apply ---


async def _apply_diff(
    *,
    diff: _ReconcileDiff,
    entry,
    cfg,
    now: int,
) -> None:
    """mutate db and discord per the diff. caller already holds the per-message lock.

    add/replace upserts the new ReactionDocument with the live emoji's
    *current* config weight (point_value snapshot). source_message_id and
    source_channel_id mirror the entry's location since reconcile observes
    the original message; redirect-source records (board posts, /stars
    displays) are handled by the watcher path.
    """
    from doom_bot.ccboard.watcher import _safe_remove_reaction

    reaction_repo = ccboard._reaction_repo
    if reaction_repo is None:
        raise RuntimeError('ccboard reaction repo not initialized')

    # adds
    for live in diff.to_add:
        point_value = cfg.emojis[live.emoji_str] + (cfg.super_bonus if live.is_super else 0)
        await reaction_repo.upsert_active(
            ReactionDocument(
                message_id=entry.message_id,
                user_id=live.user_id,
                guild_id=entry.guild_id,
                author_id=entry.author_id,
                emoji_str=live.emoji_str,
                is_super=live.is_super,
                point_value=point_value,
                reacted_at=now,
                removed=False,
                removed_at=None,
                source_message_id=entry.message_id,
                source_channel_id=entry.channel_id,
            )
        )

    # replaces — soft-delete old, upsert new under the unique (message, user) key
    for live, db_row in diff.to_replace:
        await reaction_repo.soft_delete(entry.message_id, db_row.user_id, expected_emoji=db_row.emoji_str, now=now)
        point_value = cfg.emojis[live.emoji_str] + (cfg.super_bonus if live.is_super else 0)
        await reaction_repo.upsert_active(
            ReactionDocument(
                message_id=entry.message_id,
                user_id=live.user_id,
                guild_id=entry.guild_id,
                author_id=entry.author_id,
                emoji_str=live.emoji_str,
                is_super=live.is_super,
                point_value=point_value,
                reacted_at=now,
                removed=False,
                removed_at=None,
                source_message_id=entry.message_id,
                source_channel_id=entry.channel_id,
            )
        )

    # soft-deletes (only present when partial=False per _compute_diff)
    for db_row in diff.to_remove:
        await reaction_repo.soft_delete(entry.message_id, db_row.user_id, expected_emoji=db_row.emoji_str, now=now)

    # discord-side strips: invalid live rows (bot/self) and one-vote extras
    for live in diff.to_strip_from_discord:
        await _safe_remove_reaction(entry.channel_id, entry.message_id, live.user_id, live.emoji_str)
    for live in diff.to_strip_extras:
        await _safe_remove_reaction(entry.channel_id, entry.message_id, live.user_id, live.emoji_str)


# --- Task ---


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

    async def reconcile_entry(self, guild_id: int, message_id: int, *, dry_run: bool = True) -> PassResult:  # noqa: PLR0911 - branchy validation chain returns early on each missing precondition
        """diff one entry's reactions against live discord; optionally apply.

        always takes the per-message lock. dry_run=True (the default)
        computes the diff and returns it without mutating anything. partial
        discord pagination degrades to add+replace-only so phantom-vote
        wipeouts are impossible from incomplete data.
        """
        if ccboard._entry_repo is None or ccboard._reaction_repo is None:
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary='Failed: ccboard repos not initialized')

        try:
            guild_cfg = config.guild(guild_id)
        except UnauthorizedGuild:
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary=f'Failed: guild {guild_id} unauthorized')
        cfg = guild_cfg.ccboard
        if not cfg.enabled:
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary='Failed: ccboard disabled for this guild')
        if not cfg.emojis:
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary='Failed: ccboard.emojis is empty; configure weights first')

        entry = await ccboard._entry_repo.get(message_id)
        if entry is None:
            return PassResult(kind='reconcile_entry', dry_run=dry_run, summary=f'Failed: no ccboard entry for message {message_id}')

        lock = ccboard.get_lock(message_id)
        async with lock:
            discord_msg = await _fetch_discord_message(entry.guild_id, entry.channel_id, entry.message_id)
            if discord_msg is None:
                return PassResult(
                    kind='reconcile_entry',
                    dry_run=dry_run,
                    summary=f'Failed: discord message {message_id} unavailable; consider /fix ccboard purge if it is gone for good',
                )

            configured = set(cfg.emojis)
            live_rows, partial = await _collect_live_reactions(discord_msg, configured_emojis=configured)
            db_active_list = await ccboard._reaction_repo.list_for_message(entry.message_id, include_removed=False)
            db_active: dict[int, ReactionDocument] = {row.user_id: row for row in db_active_list}

            credited = _credited_author_id(entry)
            diff = _compute_diff(live_rows=live_rows, db_active=db_active, credited_author_id=credited, partial=partial)
            details = _diff_details(diff, partial=partial)

            no_change = not diff.to_add and not diff.to_replace and not diff.to_remove and not diff.to_strip_from_discord and not diff.to_strip_extras

            if dry_run or no_change:
                summary = _summarize_diff(diff, partial=partial, dry_run=True, message_id=message_id)
                logger.info(f'ccboard auditor: reconcile_entry dry_run guild={guild_id} {summary}')
                return PassResult(kind='reconcile_entry', dry_run=True, mutated=False, summary=summary, details=details)

            now = int(time.time())
            await _apply_diff(diff=diff, entry=entry, cfg=cfg, now=now)
            net, positive = await ccboard._reaction_repo.aggregate_points(entry.message_id)
            await ccboard._entry_repo.set_points(entry.message_id, net_points=net, positive_points=positive)
            await ccboard._entry_repo.mark_dirty(entry.message_id, last_reaction_at=now)
            summary = _summarize_diff(diff, partial=partial, dry_run=False, message_id=message_id)
            logger.info(f'ccboard auditor: reconcile_entry applied guild={guild_id} {summary}')
            return PassResult(kind='reconcile_entry', dry_run=False, mutated=True, summary=summary, details=details)

    async def reconcile_guild(self, guild_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.4 placeholder: reconcile every entry in a guild.

        scoped guild-wide reconcile is folded into phase 2.4's discovery
        path so the channel-history scope can be reused. today only the
        per-entry surface (`reconcile_entry`) is implemented; callers
        should pass a message_link to /fix ccboard recount.
        """
        logger.info(f'ccboard auditor: reconcile_guild stub for guild={guild_id} dry_run={dry_run}')
        return PassResult(
            kind='reconcile_guild',
            dry_run=dry_run,
            summary='stub: guild-wide reconcile is phase 2.4; pass a message_link to /fix ccboard recount for per-entry reconcile',
        )

    async def recount_entry(self, guild_id: int, message_id: int, *, dry_run: bool = True) -> PassResult:
        """phase 2.3 placeholder: re-snapshot point_value for stale records.

        per the phase 2.1 verdict (option B+), recount is targeted via the
        staleness predicate `(last_recounted_at or reacted_at) < cfg.weights_updated_at`.
        the data-model fields (`ReactionDocument.last_recounted_at`,
        `GuildCCBoard.weights_updated_at`) and the watcher stamp land in
        phase 2.3 alongside the implementation.
        """
        logger.info(f'ccboard auditor: recount_entry stub for guild={guild_id} message={message_id} dry_run={dry_run}')
        return PassResult(
            kind='recount_entry',
            dry_run=dry_run,
            summary='stub: per-entry recount is phase 2.3; semantic approved (option B+)',
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
