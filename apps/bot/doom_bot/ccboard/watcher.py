# SPDX-License-Identifier: Apache-2.0
"""doom_bot.ccboard.watcher | reaction event handlers for the ccboard system."""

import time

import discord

from attu_models import (
    BoardEntryDocument,
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
    ReactionDocument,
)
from doom_bot import ccboard, config
from doom_bot.logging import get_logger


logger = get_logger(__name__)


# --- Repo Access ---


def _get_reaction_repo():
    if ccboard._reaction_repo is None:
        raise RuntimeError('ccboard reaction repo not initialized')
    return ccboard._reaction_repo


def _get_entry_repo():
    if ccboard._entry_repo is None:
        raise RuntimeError('ccboard entry repo not initialized')
    return ccboard._entry_repo


def _get_message_repo():
    # imported here so ccboard.watcher can be imported before doom_bot.client.messages
    # finishes wiring its module-level singleton during startup
    from doom_bot.client.messages import _get_repo as _msg_repo

    return _msg_repo()


# --- Discord Helpers ---


async def _fetch_message_from_discord(message_id: int, channel_id: int, guild_id: int) -> MessageDocument | None:
    """fetch a discord message and convert to MessageDocument; None on any failure"""
    from doom_bot.client.core import bot

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'ccboard: channel {channel_id} unavailable: {err}')
        return None
    if not isinstance(channel, discord.abc.Messageable):
        return None

    try:
        msg = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'ccboard: discord fetch failed for {message_id}: {err}')
        return None

    return MessageDocument(
        message_id=msg.id,
        guild_id=guild_id,
        channel_id=msg.channel.id,
        author=MessageAuthor(id=msg.author.id, name=msg.author.name, bot=msg.author.bot),
        content=MessageContent(text=msg.content or ''),
        refs=MessageRefs(reply_to=msg.reference.message_id if msg.reference else None),
        created_at=int(msg.created_at.timestamp()),
    )


async def _resolve_snapshot(message_id: int, channel_id: int, guild_id: int) -> MessageDocument | None:
    """try the messages collection first, then fall back to a discord fetch"""
    msg_repo = _get_message_repo()
    doc = await msg_repo.get(message_id)
    if doc is not None:
        return doc
    return await _fetch_message_from_discord(message_id, channel_id, guild_id)


async def _resolve_reply_snapshot(snapshot: MessageDocument, guild_id: int) -> MessageDocument | None:
    """fetch the reply target's MessageDocument when snapshot.refs.reply_to is set"""
    if snapshot.refs.reply_to is None:
        return None
    msg_repo = _get_message_repo()
    doc = await msg_repo.get(snapshot.refs.reply_to)
    if doc is not None:
        return doc
    return await _fetch_message_from_discord(snapshot.refs.reply_to, snapshot.channel_id, guild_id)


async def _remove_reaction_from_discord(channel_id: int, message_id: int, user_id: int, emoji_str: str) -> bool:
    """remove a reaction from discord. caller must register the pending key first.
    returns True on success; on failure the pending key is discarded by the caller's
    helper (see _safe_remove_reaction)."""
    from doom_bot.client.core import bot

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        message = channel.get_partial_message(message_id)  # type: ignore[union-attr]
        await message.remove_reaction(emoji_str, discord.Object(id=user_id))
        return True
    except Exception as err:
        logger.debug(f'ccboard: could not remove {emoji_str} from {user_id} on {message_id}: {err}')
        return False


async def _safe_remove_reaction(channel_id: int, message_id: int, user_id: int, emoji_str: str) -> bool:
    """register pending key, attempt removal, discard the key on failure.
    returns True if discord accepted the removal."""
    ccboard.register_pending_removal(channel_id, message_id, user_id, emoji_str)
    ok = await _remove_reaction_from_discord(channel_id, message_id, user_id, emoji_str)
    if not ok:
        ccboard.discard_pending_removal(channel_id, message_id, user_id, emoji_str)
    return ok


# --- Redirect ---


async def _resolve_redirect(channel_id: int, message_id: int, ccboard_channel_id: int) -> tuple[int, int, int, int]:
    """resolve reaction location through any redirect to the original message.

    returns (real_message_id, real_channel_id, source_message_id, source_channel_id)
    where the source_* fields preserve the physical discord location and the real_*
    fields point at the original message after redirect resolution.
    """
    entry_repo = _get_entry_repo()
    source_message_id = message_id
    source_channel_id = channel_id

    # reaction on the ccboard channel itself - look up by starboard_message_id
    if ccboard_channel_id and channel_id == ccboard_channel_id:
        entry = await entry_repo.get_by_starboard_message(message_id)
        if entry is not None:
            return entry.message_id, entry.channel_id, source_message_id, source_channel_id

    # reaction on a /stars random/lost display message
    entry = await entry_repo.get_by_display_message(message_id)
    if entry is not None:
        return entry.message_id, entry.channel_id, source_message_id, source_channel_id

    return message_id, channel_id, source_message_id, source_channel_id


# --- Backfill ---


async def _backfill_existing_reactions(
    *,
    real_message_id: int,
    real_channel_id: int,
    guild_id: int,
    snapshot: MessageDocument,
    effective_author_id: int | None,
    cfg,
    skip_user: int,
    skip_emoji: str,
    now: int,
) -> None:
    """walk the discord message's existing reactions and import them as ReactionDocuments.

    skips (skip_user, skip_emoji) since the caller is mid-handle for that pair.
    bot reactors are filtered. self-stars (reactor == effective author) are filtered.
    one-vote enforcement is applied per-user across emojis.
    """
    from doom_bot.client.core import bot

    try:
        channel = bot.get_channel(real_channel_id)
        if channel is None:
            channel = await bot.fetch_channel(real_channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            return
        discord_msg = await channel.fetch_message(real_message_id)
    except Exception as err:
        logger.debug(f'ccboard: backfill fetch failed for {real_message_id}: {err}')
        return

    reaction_repo = _get_reaction_repo()
    credited_author_id = effective_author_id if effective_author_id is not None else snapshot.author.id

    # tracks (user_id) -> first emoji seen this pass; subsequent reactions for the same
    # user are skipped to honor one-vote-per-message even at backfill time
    seen_users: dict[int, str] = {}
    backfilled = 0

    for reaction in discord_msg.reactions:
        emoji = str(reaction.emoji)
        if emoji not in cfg.emojis:
            continue
        is_super = bool(getattr(reaction, 'is_burst', False))
        try:
            users_iter = reaction.users()
        except Exception as err:
            logger.debug(f'ccboard: backfill users() failed for {emoji} on {real_message_id}: {err}')
            continue
        async for user in users_iter:
            if user.bot:
                continue
            if user.id == credited_author_id:
                continue
            if user.id == skip_user and emoji == skip_emoji:
                continue
            if user.id in seen_users:
                continue
            seen_users[user.id] = emoji
            point_value = cfg.emojis[emoji] + (cfg.super_bonus if is_super else 0)
            await reaction_repo.upsert_active(
                ReactionDocument(
                    message_id=real_message_id,
                    user_id=user.id,
                    guild_id=guild_id,
                    author_id=snapshot.author.id,
                    emoji_str=emoji,
                    is_super=is_super,
                    point_value=point_value,
                    reacted_at=now,
                    removed=False,
                    removed_at=None,
                    source_message_id=real_message_id,
                    source_channel_id=real_channel_id,
                )
            )
            backfilled += 1

    if backfilled:
        logger.info(f'ccboard: backfilled {backfilled} existing reaction(s) on message {real_message_id}')


async def _ensure_entry(
    *,
    real_message_id: int,
    real_channel_id: int,
    guild_id: int,
    cfg,
    skip_user: int,
    skip_emoji: str,
    now: int,
) -> BoardEntryDocument | None:
    """return the existing entry or create one by snapshotting the message.

    on first creation, walks discord's reactions and imports them via _backfill_existing_reactions.
    returns None if the snapshot cannot be resolved (deleted message with no db record).
    """
    entry_repo = _get_entry_repo()
    existing = await entry_repo.get(real_message_id)
    if existing is not None:
        return existing

    snapshot = await _resolve_snapshot(real_message_id, real_channel_id, guild_id)
    if snapshot is None:
        logger.debug(f'ccboard: cannot snapshot {real_message_id}; skipping')
        return None

    reply_snapshot = await _resolve_reply_snapshot(snapshot, guild_id)

    # attribution: bot-authored replies credit the reply target's author
    effective_author_id: int | None = None
    if snapshot.author.bot and reply_snapshot is not None:
        effective_author_id = reply_snapshot.author.id

    entry = BoardEntryDocument(
        message_id=real_message_id,
        channel_id=real_channel_id,
        guild_id=guild_id,
        author_id=snapshot.author.id,
        effective_author_id=effective_author_id,
        starboard_message_id=None,
        display_message_ids=[],
        net_points=0,
        positive_points=0,
        last_reaction_at=now,
        last_synced_at=0,
        is_dirty=True,
        reply_created=False,
        snapshot=snapshot,
        reply_snapshot=reply_snapshot,
    )
    await entry_repo.upsert(entry)

    await _backfill_existing_reactions(
        real_message_id=real_message_id,
        real_channel_id=real_channel_id,
        guild_id=guild_id,
        snapshot=snapshot,
        effective_author_id=effective_author_id,
        cfg=cfg,
        skip_user=skip_user,
        skip_emoji=skip_emoji,
        now=now,
    )

    return entry


# --- Recompute ---


async def _recompute_and_mark(message_id: int, *, now: int) -> None:
    """re-aggregate points from active reactions and flag the entry for the manager"""
    reaction_repo = _get_reaction_repo()
    entry_repo = _get_entry_repo()
    net, positive = await reaction_repo.aggregate_points(message_id)
    await entry_repo.set_points(message_id, net_points=net, positive_points=positive)
    await entry_repo.mark_dirty(message_id, last_reaction_at=now)


# --- Public Handlers ---


async def handle_reaction_add(  # noqa: PLR0911 - early returns mirror the 10-step spec flow; collapsing them obscures the gating order
    guild_id: int,
    channel_id: int,
    message_id: int,
    user_id: int,
    emoji_str: str,
    is_burst: bool,
    is_bot: bool,
) -> None:
    """process a raw_reaction_add event for a configured ccboard emoji.

    follows the 10-step flow in notes/plans/ccboard.md: redirect resolution, snapshot
    backfill, self-star auto-remove, one-vote enforcement, upsert, recompute.
    """
    try:
        guild_cfg = config.guild(guild_id)
    except Exception:
        return
    cfg = guild_cfg.ccboard
    if not cfg.enabled:
        return
    if emoji_str not in cfg.emojis:
        return
    if is_bot:
        return

    # step 4 - redirect to the original message; preserve physical location
    real_message_id, real_channel_id, source_message_id, source_channel_id = await _resolve_redirect(channel_id, message_id, cfg.channel_id)

    # step 5 - acquire the per-message lock keyed on the resolved message id
    lock = ccboard.get_lock(real_message_id)
    async with lock:
        now = int(time.time())

        # step 6 - backfill: ensure the entry exists, snapshot the message if first-touch
        entry = await _ensure_entry(
            real_message_id=real_message_id,
            real_channel_id=real_channel_id,
            guild_id=guild_id,
            cfg=cfg,
            skip_user=user_id,
            skip_emoji=emoji_str,
            now=now,
        )
        if entry is None:
            return

        credited_author_id = entry.effective_author_id if entry.effective_author_id is not None else entry.snapshot.author.id

        # step 7 - self-star: register pending key on the *physical* location, remove, return
        if user_id == credited_author_id:
            await _safe_remove_reaction(source_channel_id, source_message_id, user_id, emoji_str)
            return

        reaction_repo = _get_reaction_repo()
        existing = await reaction_repo.get_active(real_message_id, user_id)
        point_value = cfg.emojis[emoji_str] + (cfg.super_bonus if is_burst else 0)

        # step 8 - one-vote enforcement
        if existing is not None and existing.emoji_str == emoji_str:
            # same-emoji re-react: refresh in place. discord already enforces one
            # reaction-per-emoji-per-user so no removal is needed. point_value is
            # re-snapshotted from current cfg (may differ from existing.point_value
            # if cfg.emojis weights changed since last reaction); stamp
            # last_recounted_at so the auditor's recount staleness predicate sees
            # this record as fresh.
            refreshed = ReactionDocument(
                message_id=real_message_id,
                user_id=user_id,
                guild_id=guild_id,
                author_id=entry.author_id,
                emoji_str=emoji_str,
                is_super=is_burst,
                point_value=point_value,
                reacted_at=now,
                removed=False,
                removed_at=None,
                source_message_id=source_message_id,
                source_channel_id=source_channel_id,
                last_recounted_at=now,
            )
            await reaction_repo.upsert_active(refreshed)
            await _recompute_and_mark(real_message_id, now=now)
            return

        if existing is not None and existing.emoji_str != emoji_str:
            # different-emoji vote change: remove the OLD reaction from its physical location.
            # db correctness wins over discord visual consistency - on api failure we still
            # soft-delete the old doc and proceed.
            await _safe_remove_reaction(
                existing.source_channel_id,
                existing.source_message_id,
                user_id,
                existing.emoji_str,
            )
            await reaction_repo.soft_delete(real_message_id, user_id, expected_emoji=existing.emoji_str, now=now)

        # step 9 - upsert the new ReactionDocument
        new_doc = ReactionDocument(
            message_id=real_message_id,
            user_id=user_id,
            guild_id=guild_id,
            author_id=entry.author_id,
            emoji_str=emoji_str,
            is_super=is_burst,
            point_value=point_value,
            reacted_at=now,
            removed=False,
            removed_at=None,
            source_message_id=source_message_id,
            source_channel_id=source_channel_id,
        )
        await reaction_repo.upsert_active(new_doc)

        # step 10 - recompute and mark dirty so the manager picks it up
        await _recompute_and_mark(real_message_id, now=now)


async def handle_reaction_remove(  # noqa: PLR0911 - early returns mirror the 4-step spec flow; collapsing them hides the pending-key short-circuit
    guild_id: int,
    channel_id: int,
    message_id: int,
    user_id: int,
    emoji_str: str,
) -> None:
    """process a raw_reaction_remove event for a configured ccboard emoji"""
    try:
        guild_cfg = config.guild(guild_id)
    except Exception:
        return
    cfg = guild_cfg.ccboard
    if not cfg.enabled:
        return
    if emoji_str not in cfg.emojis:
        return

    # step 1 - consume any pending bot-initiated removal echo for this physical location
    if ccboard.consume_pending_removal(channel_id, message_id, user_id, emoji_str):
        return

    # step 2 - redirect to the original message
    real_message_id, _real_channel_id, _src_message_id, _src_channel_id = await _resolve_redirect(channel_id, message_id, cfg.channel_id)

    # step 3 - lock on the resolved message
    lock = ccboard.get_lock(real_message_id)
    async with lock:
        now = int(time.time())
        reaction_repo = _get_reaction_repo()

        # step 4 - find the active reaction; reject stale echoes via expected_emoji
        existing = await reaction_repo.get_active(real_message_id, user_id)
        if existing is None:
            return
        if existing.emoji_str != emoji_str:
            # stale echo from a vote change that already superseded this emoji
            return

        deleted = await reaction_repo.soft_delete(real_message_id, user_id, expected_emoji=emoji_str, now=now)
        if deleted is None:
            return
        await _recompute_and_mark(real_message_id, now=now)


async def handle_reaction_clear(guild_id: int, channel_id: int, message_id: int) -> None:
    """process a raw_reaction_clear event - all emojis cleared on a message"""
    try:
        guild_cfg = config.guild(guild_id)
    except Exception:
        return
    cfg = guild_cfg.ccboard
    if not cfg.enabled:
        return

    real_message_id, _real_channel_id, _src_message_id, _src_channel_id = await _resolve_redirect(channel_id, message_id, cfg.channel_id)

    lock = ccboard.get_lock(real_message_id)
    async with lock:
        now = int(time.time())
        reaction_repo = _get_reaction_repo()
        affected = await reaction_repo.soft_delete_all_for_message(real_message_id, now=now)
        if affected == 0:
            return
        await _recompute_and_mark(real_message_id, now=now)


async def handle_reaction_clear_emoji(guild_id: int, channel_id: int, message_id: int, emoji_str: str) -> None:
    """process a raw_reaction_clear_emoji event - one emoji cleared on a message"""
    try:
        guild_cfg = config.guild(guild_id)
    except Exception:
        return
    cfg = guild_cfg.ccboard
    if not cfg.enabled:
        return
    if emoji_str not in cfg.emojis:
        return

    real_message_id, _real_channel_id, _src_message_id, _src_channel_id = await _resolve_redirect(channel_id, message_id, cfg.channel_id)

    lock = ccboard.get_lock(real_message_id)
    async with lock:
        now = int(time.time())
        reaction_repo = _get_reaction_repo()
        affected = await reaction_repo.soft_delete_emoji(real_message_id, emoji_str, now=now)
        if affected == 0:
            return
        await _recompute_and_mark(real_message_id, now=now)


logger.info('registered: ccboard watcher')
