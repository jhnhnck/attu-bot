# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.auditor | discovery / reconciliation / orphan-cleanup task.

design notes (see notes/features/ccboard.md for the full correctness invariants):
  * every mutating pass takes ccboard.get_lock(message_id) just like the
    watcher and manager
  * any bot-initiated reaction removal goes through the watcher's
    _safe_remove_reaction helper so _pending_bot_removals echo-suppression
    keeps working
  * dry_run=True is the default for any pass that mutates discord state
"""

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import discord
import structlog

from nova_core import ccboard
from nova_core.ccboard.documents import ReactionDocument
from nova_core.client.core import config
from nova_core.config import UnauthorizedGuild
from nova_core.tasks.base import BaseTask


logger = structlog.stdlib.get_logger(__name__)


# --- result type ---


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


# --- internal helpers ---


def _credited_author_id(entry) -> int:
    return entry.effective_author_id if entry.effective_author_id is not None else entry.author_id


def _get_bot():
    """lazy import of the bot singleton; extracted so tests can monkeypatch it."""
    from nova_core.client.core import bot

    return bot


async def _fetch_discord_message(guild_id: int, channel_id: int, message_id: int) -> discord.Message | None:
    """fetch one discord message; return None on any expected failure mode"""
    from nova_core.client.core import bot

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
    """one user/emoji pair seen on discord during reconcile."""

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

    one-vote enforcement is NOT applied here - caller resolves it after
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
            logger.warning(f'ccboard auditor: reaction.users() failed for {emoji} on {discord_msg.id}: {err}; treating as partial')
            partial = True
            continue
        try:
            async for user in users_iter:
                rows.append(_LiveReaction(user_id=user.id, emoji_str=emoji, is_super=is_super, is_bot_reactor=bool(getattr(user, 'bot', False))))
        except Exception as err:
            logger.warning(f'ccboard auditor: pagination failed mid-stream for {emoji} on {discord_msg.id}: {err}; treating as partial')
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
    """structured per-user diff between live discord and the database."""

    # users in live but absent from db (or in db but soft-deleted) - would create new
    to_add: list[_LiveReaction] = field(default_factory=list)
    # users in both, but the live emoji or super flag differs from the db record
    to_replace: list[tuple[_LiveReaction, ReactionDocument]] = field(default_factory=list)
    # users in db active state but missing from live - would soft-delete
    to_remove: list[ReactionDocument] = field(default_factory=list)
    # invalid live rows (bot reactor, self-reaction); would auto-remove from discord
    to_strip_from_discord: list[_LiveReaction] = field(default_factory=list)
    # users with multiple live rows; the extras would be auto-removed from discord
    to_strip_extras: list[_LiveReaction] = field(default_factory=list)
    # users in both with matching emoji+super, but the db record's freshness predates
    # cfg.weights_updated_at - re-snapshot point_value with current weights and stamp last_recounted_at
    to_recount: list[ReactionDocument] = field(default_factory=list)
    # users in both with matching emoji+super - no change needed (counted, not enumerated)
    matching_count: int = 0


def _is_stale(db_row: ReactionDocument, weights_updated_at: int) -> bool:
    """staleness predicate.

    a record is stale when its last point_value snapshot predates the most recent
    config weight change. None last_recounted_at falls back to reacted_at - the
    record was snapshotted at reaction time and never re-snapshotted.
    weights_updated_at == 0 short-circuits to "never stale" so guilds that have
    not changed weights since the field was added pay no recount cost.
    """
    if weights_updated_at <= 0:
        return False
    effective = db_row.last_recounted_at if db_row.last_recounted_at is not None else db_row.reacted_at
    return effective < weights_updated_at


def _classify_existing_match(
    diff: _ReconcileDiff,
    *,
    live_row: _LiveReaction,
    db_row: ReactionDocument,
    weights_updated_at: int,
) -> None:
    """one user is in both live and db: place them in to_replace, to_recount, or matching"""
    if db_row.emoji_str == live_row.emoji_str and db_row.is_super == live_row.is_super:
        if _is_stale(db_row, weights_updated_at):
            diff.to_recount.append(db_row)
        else:
            diff.matching_count += 1
        return
    diff.to_replace.append((live_row, db_row))


def _compute_diff(
    *,
    live_rows: list[_LiveReaction],
    db_active: dict[int, ReactionDocument],
    credited_author_id: int,
    partial: bool,
    weights_updated_at: int = 0,
) -> _ReconcileDiff:
    """pure function: compare live discord state to db state.

    callers in dry-run mode use the diff to render a summary. callers in
    apply mode use the diff as the mutation plan. partial=True suppresses
    `to_remove` so missing-from-live records (which might be missing only
    because pagination failed) are not soft-deleted.

    weights_updated_at drives the recount staleness predicate. matching records whose effective freshness predates this
    timestamp move from `matching_count` to `to_recount` so the apply path
    re-snapshots `point_value`.
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

    # diff per user: add (new), or hand off to _classify_existing_match
    for user_id, live_row in valid_live.items():
        db_row = db_active.get(user_id)
        if db_row is None:
            diff.to_add.append(live_row)
            continue
        _classify_existing_match(diff, live_row=live_row, db_row=db_row, weights_updated_at=weights_updated_at)

    # remove side - only when not partial
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
        f'recount={len(diff.to_recount)}',
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
        'recount': len(diff.to_recount),
        'match': diff.matching_count,
        'strip_invalid': len(diff.to_strip_from_discord),
        'strip_extras': len(diff.to_strip_extras),
        'partial': partial,
    }


# --- apply ---


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
    from nova_core.ccboard.watcher import _safe_remove_reaction

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

    # replaces - soft-delete old, upsert new under the unique (message, user) key
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

    # recounts - same emoji/is_super as the existing record, fresh point_value from current cfg,
    # last_recounted_at stamped to now. structurally a soft-delete + upsert under the same
    # (message, user) unique key, identical to the replace bucket but without changing emoji.
    for db_row in diff.to_recount:
        new_point_value = cfg.emojis[db_row.emoji_str] + (cfg.super_bonus if db_row.is_super else 0)
        await reaction_repo.soft_delete(entry.message_id, db_row.user_id, expected_emoji=db_row.emoji_str, now=now)
        await reaction_repo.upsert_active(
            ReactionDocument(
                message_id=entry.message_id,
                user_id=db_row.user_id,
                guild_id=entry.guild_id,
                author_id=entry.author_id,
                emoji_str=db_row.emoji_str,
                is_super=db_row.is_super,
                point_value=new_point_value,
                reacted_at=db_row.reacted_at,
                removed=False,
                removed_at=None,
                source_message_id=db_row.source_message_id,
                source_channel_id=db_row.source_channel_id,
                last_recounted_at=now,
            )
        )

    # discord-side strips: invalid live rows (bot/self) and one-vote extras
    for live in diff.to_strip_from_discord:
        await _safe_remove_reaction(entry.channel_id, entry.message_id, live.user_id, live.emoji_str)
    for live in diff.to_strip_extras:
        await _safe_remove_reaction(entry.channel_id, entry.message_id, live.user_id, live.emoji_str)


# --- task ---


class AuditorTask(BaseTask):
    """auditor for ccboard drift between live discord state and the database.

    registered in the scheduler with `interval=None` so it never fires on a
    timer; every pass is invoked from a slash command.
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
            diff = _compute_diff(
                live_rows=live_rows,
                db_active=db_active,
                credited_author_id=credited,
                partial=partial,
                weights_updated_at=cfg.weights_updated_at,
            )
            details = _diff_details(diff, partial=partial)

            no_change = not diff.to_add and not diff.to_replace and not diff.to_remove and not diff.to_recount and not diff.to_strip_from_discord and not diff.to_strip_extras

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
        """reconcile every entry in a guild.

        calls reconcile_entry per entry under a 90s per-guild time budget.
        guild-wide recount is inherited free - reconcile_entry already
        consults cfg.weights_updated_at via the staleness predicate in
        _compute_diff, so a weights bump before running this will
        re-snapshot every stale active record automatically.
        """
        if ccboard._entry_repo is None or ccboard._reaction_repo is None:
            return PassResult(kind='reconcile_guild', dry_run=dry_run, summary='Failed: ccboard repos not initialized')
        try:
            guild_cfg = config.guild(guild_id)
        except UnauthorizedGuild:
            return PassResult(kind='reconcile_guild', dry_run=dry_run, summary=f'Failed: guild {guild_id} unauthorized')
        cfg = guild_cfg.ccboard
        if not cfg.enabled:
            return PassResult(kind='reconcile_guild', dry_run=dry_run, summary='Failed: ccboard disabled for this guild')
        if not cfg.emojis:
            return PassResult(kind='reconcile_guild', dry_run=dry_run, summary='Failed: ccboard.emojis is empty; configure weights first')

        entries = await ccboard._entry_repo.all_for_guild(guild_id)
        if not entries:
            return PassResult(kind='reconcile_guild', dry_run=dry_run, summary=f'guild={guild_id} no entries found')

        _BUDGET_SECONDS = 90.0
        start = time.monotonic()
        processed = mutated_count = skipped = 0

        for entry in entries:
            if time.monotonic() - start >= _BUDGET_SECONDS:
                skipped = len(entries) - processed
                logger.info(f'ccboard auditor: reconcile_guild budget {_BUDGET_SECONDS}s exhausted after {processed}/{len(entries)} guild={guild_id}')
                break
            result = await self.reconcile_entry(guild_id, entry.message_id, dry_run=dry_run)
            processed += 1
            if result.mutated:
                mutated_count += 1

        elapsed = time.monotonic() - start
        mode = 'dry_run' if dry_run else 'applied'
        extra = ' (budget exhausted — re-run to continue)' if skipped else ''
        summary = f'guild={guild_id} processed={processed}/{len(entries)} mutated={mutated_count} skipped={skipped} elapsed={elapsed:.1f}s [{mode}]{extra}'
        logger.info(f'ccboard auditor: reconcile_guild {summary}')
        return PassResult(
            kind='reconcile_guild',
            dry_run=dry_run,
            mutated=mutated_count > 0,
            summary=summary,
            details={'processed': processed, 'total': len(entries), 'mutated': mutated_count, 'skipped': skipped, 'elapsed_s': round(elapsed, 1)},
        )

    async def recount_entry(self, guild_id: int, message_id: int, *, dry_run: bool = True) -> PassResult:
        """thin wrapper around `reconcile_entry`.

        recount is no longer a separate codepath. `reconcile_entry` always
        consults `cfg.weights_updated_at`, and stale records (those whose
        `(last_recounted_at or reacted_at) < cfg.weights_updated_at`) flow
        through the `to_recount` bucket inside the existing diff. callers
        that only care about recount semantics can call this method instead
        of `reconcile_entry`; the only difference is the `kind` tag on the
        returned `PassResult`, which keeps the slash-command response
        readable.
        """
        result = await self.reconcile_entry(guild_id, message_id, dry_run=dry_run)
        return PassResult(
            kind='recount_entry',
            dry_run=result.dry_run,
            mutated=result.mutated,
            summary=result.summary,
            details=result.details,
        )

    async def discover_guild(self, guild_id: int, *, dry_run: bool = True, lookback_days: int = 30) -> PassResult:  # noqa: PLR0912, PLR0915 - channel-history scan with per-channel and per-message error/skip branches
        """scan recently-active channels for missed reactions.

        scoped to channels that already have ccboard entries - never performs
        an unbounded guild-wide scan (the pre-mortem flagged that as a
        high-severity performance risk). for each channel, walks the last
        `lookback_days` days of message history; messages with configured-emoji
        reactions that have no BoardEntryDocument are counted (dry_run=True)
        or created via the watcher's _ensure_entry backfill path (dry_run=False).

        rate-limit waits are logged; scan respects a 90s time budget and
        reports when exhausted so callers know to re-run.
        """
        if ccboard._entry_repo is None or ccboard._reaction_repo is None:
            return PassResult(kind='discover_guild', dry_run=dry_run, summary='Failed: ccboard repos not initialized')
        try:
            guild_cfg = config.guild(guild_id)
        except UnauthorizedGuild:
            return PassResult(kind='discover_guild', dry_run=dry_run, summary=f'Failed: guild {guild_id} unauthorized')
        cfg = guild_cfg.ccboard
        if not cfg.enabled:
            return PassResult(kind='discover_guild', dry_run=dry_run, summary='Failed: ccboard disabled for this guild')
        if not cfg.emojis:
            return PassResult(kind='discover_guild', dry_run=dry_run, summary='Failed: ccboard.emojis is empty; configure weights first')

        channel_ids = await ccboard._entry_repo.distinct_channel_ids(guild_id)
        if not channel_ids:
            return PassResult(kind='discover_guild', dry_run=dry_run, summary=f'guild={guild_id} no channels with ccboard entries; nothing to discover')

        _BUDGET_SECONDS = 90.0
        cutoff = datetime.now(tz=UTC) - timedelta(days=lookback_days)
        configured = set(cfg.emojis)
        bot = _get_bot()

        start = time.monotonic()
        channels_scanned = scanned = found = created = 0
        budget_exhausted = False

        for channel_id in channel_ids:
            if time.monotonic() - start >= _BUDGET_SECONDS:
                budget_exhausted = True
                break

            channel = bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await bot.fetch_channel(channel_id)
                except (discord.NotFound, discord.Forbidden) as err:
                    logger.debug(f'ccboard auditor: discovery channel {channel_id} unavailable guild={guild_id}: {err}')
                    continue
                except discord.HTTPException as err:
                    retry = getattr(err, 'retry_after', None)
                    if retry:
                        logger.info(f'ccboard auditor: discovery rate-limited fetching channel {channel_id} guild={guild_id}; retry_after={retry:.1f}s')
                    else:
                        logger.warning(f'ccboard auditor: discovery fetch channel {channel_id} failed guild={guild_id}: {err}')
                    continue
            if not isinstance(channel, discord.abc.Messageable):
                continue

            channels_scanned += 1
            try:
                async for message in channel.history(limit=None, after=cutoff, oldest_first=True):
                    if time.monotonic() - start >= _BUDGET_SECONDS:
                        budget_exhausted = True
                        break

                    if not any(str(r.emoji) in configured for r in message.reactions):
                        continue

                    scanned += 1
                    if await ccboard._entry_repo.get(message.id) is not None:
                        continue  # already tracked

                    found += 1
                    logger.info(f'ccboard auditor: discovery untracked message={message.id} ch={channel_id} guild={guild_id}')
                    if not dry_run:
                        from nova_core.ccboard.watcher import _ensure_entry

                        now = int(time.time())
                        lock = ccboard.get_lock(message.id)
                        async with lock:
                            entry = await _ensure_entry(
                                real_message_id=message.id,
                                real_channel_id=channel_id,
                                guild_id=guild_id,
                                cfg=cfg,
                                skip_user=0,
                                skip_emoji='',
                                now=now,
                            )
                        if entry is not None:
                            created += 1
                            logger.info(f'ccboard auditor: discovery created entry for {message.id} guild={guild_id}')

            except discord.Forbidden as err:
                logger.warning(f'ccboard auditor: discovery history forbidden ch={channel_id} guild={guild_id}: {err}')
                continue
            except discord.HTTPException as err:
                retry = getattr(err, 'retry_after', None)
                if retry:
                    logger.info(f'ccboard auditor: discovery rate-limited history ch={channel_id} guild={guild_id}; retry_after={retry:.1f}s')
                else:
                    logger.warning(f'ccboard auditor: discovery history failed ch={channel_id} guild={guild_id}: {err}')
                continue

            if budget_exhausted:
                break

        elapsed = time.monotonic() - start
        mode = 'dry_run' if dry_run else 'applied'
        extra = ' (budget exhausted — re-run to continue)' if budget_exhausted else ''
        action = 'would_create' if dry_run else 'created'
        summary = f'guild={guild_id} channels={channels_scanned} scanned={scanned} untracked={found} {action}={created} elapsed={elapsed:.1f}s [{mode}]{extra}'
        logger.info(f'ccboard auditor: discover_guild {summary}')
        return PassResult(
            kind='discover_guild',
            dry_run=dry_run,
            mutated=created > 0,
            summary=summary,
            details={'channels': channels_scanned, 'scanned': scanned, 'found': found, 'created': created, 'elapsed_s': round(elapsed, 1), 'budget_exhausted': budget_exhausted},
        )

    async def cleanup_orphans(self, guild_id: int, *, dry_run: bool = True, grace_days: int = 7) -> PassResult:  # noqa: PLR0911, PLR0912 - channel-scan with per-precondition early returns and per-failure-mode error branches
        """scan the ccboard channel for bot-authored posts with no DB twin.

        only considers posts older than `grace_days` so freshly-created posts
        whose entry write failed are not deleted before the manager retries.
        dry_run=True (the default) lists candidates without deleting anything.
        every deletion is logged individually regardless of dry_run.
        """
        if ccboard._entry_repo is None or ccboard._reaction_repo is None:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary='Failed: ccboard repos not initialized')
        try:
            guild_cfg = config.guild(guild_id)
        except UnauthorizedGuild:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary=f'Failed: guild {guild_id} unauthorized')
        cfg = guild_cfg.ccboard
        if not cfg.enabled:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary='Failed: ccboard disabled for this guild')
        if not cfg.channel_id:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary='Failed: ccboard.channel_id not configured; cannot scan for orphan posts')

        bot = _get_bot()
        try:
            channel = bot.get_channel(cfg.channel_id)
            if channel is None:
                channel = await bot.fetch_channel(cfg.channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary=f'Failed: ccboard channel {cfg.channel_id} unavailable: {err}')
        if not isinstance(channel, discord.abc.Messageable):
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary=f'Failed: ccboard channel {cfg.channel_id} is not a text channel')

        cutoff = datetime.now(tz=UTC) - timedelta(days=grace_days)
        bot_id = bot.user.id

        _BUDGET_SECONDS = 90.0
        start = time.monotonic()
        scanned = candidates = deleted = 0
        budget_exhausted = False

        try:
            async for message in channel.history(limit=None, before=cutoff, oldest_first=False):
                if time.monotonic() - start >= _BUDGET_SECONDS:
                    budget_exhausted = True
                    break
                if message.author.id != bot_id:
                    continue
                scanned += 1
                entry = await ccboard._entry_repo.get_by_starboard_message(message.id)
                if entry is not None:
                    continue
                candidates += 1
                age_days = (datetime.now(tz=UTC) - message.created_at).days
                logger.info(f'ccboard auditor: cleanup_orphans orphan post={message.id} age={age_days}d guild={guild_id}')
                if not dry_run:
                    try:
                        await message.delete()
                        deleted += 1
                        logger.info(f'ccboard auditor: cleanup_orphans deleted orphan post={message.id} age={age_days}d guild={guild_id}')
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
                        logger.warning(f'ccboard auditor: cleanup_orphans failed to delete post={message.id}: {err}')
        except discord.Forbidden as err:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary=f'Failed: cannot read ccboard channel {cfg.channel_id}: {err}')
        except discord.HTTPException as err:
            return PassResult(kind='cleanup_orphans', dry_run=dry_run, summary=f'Failed: HTTP error reading ccboard channel {cfg.channel_id}: {err}')

        elapsed = time.monotonic() - start
        mode = 'dry_run' if dry_run else 'applied'
        extra = ' (budget exhausted — re-run to continue)' if budget_exhausted else ''
        action = 'would_delete' if dry_run else 'deleted'
        summary = f'guild={guild_id} scanned={scanned} orphans={candidates} {action}={deleted} grace={grace_days}d elapsed={elapsed:.1f}s [{mode}]{extra}'
        logger.info(f'ccboard auditor: cleanup_orphans {summary}')
        return PassResult(
            kind='cleanup_orphans',
            dry_run=dry_run,
            mutated=deleted > 0,
            summary=summary,
            details={'scanned': scanned, 'orphans': candidates, 'deleted': deleted, 'elapsed_s': round(elapsed, 1), 'budget_exhausted': budget_exhausted},
        )


# singleton instance for registration
auditor_task = AuditorTask()


logger.info('registered: ccboard auditor')
