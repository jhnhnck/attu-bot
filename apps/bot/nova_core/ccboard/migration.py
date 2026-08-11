# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.migration | one-shot starboard → ccboard data migration."""

import time

import discord
import structlog

from attu_models import (
    MessageAuthor,
    MessageContent,
    MessageDocument,
    MessageRefs,
)
from nova_core.ccboard.documents import BoardEntryDocument, ReactionDocument
from nova_core.client.core import bot, config
from nova_core.client.messages import _get_repo as _get_message_repo
from nova_core.client.starboard import _get_repo as _get_starboard_repo


logger = structlog.stdlib.get_logger(__name__)


def _get_reaction_repo():
    from nova_core import ccboard

    if ccboard._reaction_repo is None:
        raise RuntimeError('ccboard reaction repo not initialized')
    return ccboard._reaction_repo


def _get_entry_repo():
    from nova_core import ccboard

    if ccboard._entry_repo is None:
        raise RuntimeError('ccboard entry repo not initialized')
    return ccboard._entry_repo


def _placeholder_message(message_id: int, channel_id: int, guild_id: int, author_id: int) -> MessageDocument:
    """build a minimal MessageDocument when the original is unavailable from db or discord"""
    return MessageDocument(
        message_id=message_id,
        guild_id=guild_id,
        channel_id=channel_id,
        author=MessageAuthor(id=author_id, name=f'user-{author_id}', bot=False),
        content=MessageContent(text=''),
        refs=MessageRefs(),
        created_at=0,
    )


async def _fetch_message_from_discord(message_id: int, channel_id: int, guild_id: int) -> MessageDocument | None:
    """attempt to fetch a message from discord and convert it to a MessageDocument.
    returns None on any failure so the caller can fall back to a placeholder."""
    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'convert: channel {channel_id} unavailable: {err}')
        return None
    if not isinstance(channel, discord.abc.Messageable):
        return None

    try:
        msg = await channel.fetch_message(message_id)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException) as err:
        logger.debug(f'convert: discord fetch failed for {message_id}: {err}')
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


async def _resolve_message_doc(message_id: int, channel_id: int, guild_id: int, author_id: int, *, fallback_counts: dict[str, int]) -> MessageDocument:
    """try the messages collection, then discord, then a placeholder. tracks fallback path."""
    msg_repo = _get_message_repo()
    doc = await msg_repo.get(message_id)
    if doc is not None:
        return doc

    fallback_counts['discord_fetched'] += 1
    fetched = await _fetch_message_from_discord(message_id, channel_id, guild_id)
    if fetched is not None:
        return fetched

    fallback_counts['discord_fetched'] -= 1
    fallback_counts['placeholder'] += 1
    return _placeholder_message(message_id, channel_id, guild_id, author_id)


async def _resolve_reply_snapshot(snapshot: MessageDocument, guild_id: int) -> MessageDocument | None:
    """fetch the reply target's MessageDocument if snapshot has refs.reply_to set"""
    if snapshot.refs.reply_to is None:
        return None
    msg_repo = _get_message_repo()
    reply_doc = await msg_repo.get(snapshot.refs.reply_to)
    if reply_doc is not None:
        return reply_doc
    # best-effort discord fetch - the reply target is in the same channel as the snapshot
    return await _fetch_message_from_discord(snapshot.refs.reply_to, snapshot.channel_id, guild_id)


async def _build_and_upsert_entry(starred, snapshot: MessageDocument, reply_snapshot: MessageDocument | None, *, guild_id: int, now: int) -> None:
    """build a BoardEntryDocument from a StarredMessageDocument and upsert; preserves
    last_synced_at, starboard_message_id, and display_message_ids on existing entries
    so re-running the migration is idempotent."""
    entry_repo = _get_entry_repo()
    existing = await entry_repo.get(starred.message_id)
    last_synced_at = existing.last_synced_at if existing else now
    starboard_message_id = existing.starboard_message_id if existing and existing.starboard_message_id else starred.starboard_message_id
    display_message_ids = existing.display_message_ids if existing else []

    effective_author_id: int | None = None
    if snapshot.author.bot and reply_snapshot is not None:
        effective_author_id = reply_snapshot.author.id

    entry = BoardEntryDocument(
        message_id=starred.message_id,
        channel_id=starred.channel_id,
        guild_id=guild_id,
        author_id=starred.author_id,
        effective_author_id=effective_author_id,
        starboard_message_id=starboard_message_id,
        display_message_ids=display_message_ids,
        net_points=0,
        positive_points=0,
        last_reaction_at=now - 120,
        last_synced_at=last_synced_at,
        is_dirty=False,
        reply_created=starred.reply_created,
        snapshot=snapshot,
        reply_snapshot=reply_snapshot,
    )
    await entry_repo.upsert(entry)


async def _migrate_reactions_for_entry(starred, *, cfg, guild_id: int, now: int) -> tuple[int, int]:
    """write per-user ReactionDocuments for one StarredMessageDocument.

    regular reactions are written first; super reactions written second so that the
    (message_id, user_id) unique index has the super (higher-value) record win when a
    user appears in both lists for the same emoji.

    returns (reactions_migrated, skipped_unweighted)."""
    reaction_repo = _get_reaction_repo()
    migrated = 0
    skipped = 0

    for emoji_str, user_ids in starred.reactions.items():
        weight = cfg.emojis.get(emoji_str)
        if weight is None:
            skipped += len(user_ids)
            continue
        super_users_for_emoji = set(starred.super_reactions.get(emoji_str, []))
        for user_id in user_ids:
            if user_id in super_users_for_emoji:
                continue
            await reaction_repo.upsert_active(_reaction_doc(starred, emoji_str, user_id, weight=weight, is_super=False, now=now))
            migrated += 1

    for emoji_str, user_ids in starred.super_reactions.items():
        weight = cfg.emojis.get(emoji_str)
        if weight is None:
            skipped += len(user_ids)
            continue
        for user_id in user_ids:
            await reaction_repo.upsert_active(_reaction_doc(starred, emoji_str, user_id, weight=weight + cfg.super_bonus, is_super=True, now=now))
            migrated += 1

    return migrated, skipped


def _reaction_doc(starred, emoji_str: str, user_id: int, *, weight: int, is_super: bool, now: int) -> ReactionDocument:
    return ReactionDocument(
        message_id=starred.message_id,
        user_id=user_id,
        guild_id=starred.guild_id,
        author_id=starred.author_id,
        emoji_str=emoji_str,
        is_super=is_super,
        point_value=weight,
        reacted_at=now,
        removed=False,
        removed_at=None,
        source_message_id=starred.message_id,
        source_channel_id=starred.channel_id,
    )


def _empty_stats() -> dict[str, int]:
    return {
        'entries_processed': 0,
        'reactions_migrated': 0,
        'discord_fetched': 0,
        'placeholder': 0,
        'skipped_unweighted_emojis': 0,
        'skipped_no_config': 0,
    }


async def job_convert_starboard_to_ccboard(guild_id: int, status_msg: discord.Message | None = None) -> dict[str, int]:
    """one-shot migration: copy starboard records into ccboard_reactions + ccboard_entries.

    idempotent: re-running yields the same final state because every write is an upsert
    and last_synced_at / starboard_message_id are preserved on existing entries.

    returns a stats dict for the caller to render into a summary embed.
    """
    sb_repo = _get_starboard_repo()
    reaction_repo = _get_reaction_repo()
    entry_repo = _get_entry_repo()

    cfg = config.guild(guild_id).ccboard
    if not cfg.emojis:
        logger.warning(f'convert: guild {guild_id} has no ccboard.emojis configured; cannot weight reactions')
        stats = _empty_stats()
        stats['skipped_no_config'] = 1
        return stats

    starred_docs = await sb_repo.all_for_guild(guild_id)
    if not starred_docs:
        logger.info(f'convert: guild {guild_id} has no starboard records to migrate')
        return _empty_stats()

    now = int(time.time())
    fallback_counts = {'discord_fetched': 0, 'placeholder': 0}
    total_reactions = 0
    skipped_unweighted = 0

    logger.info(f'convert: starting migration for guild {guild_id}; {len(starred_docs)} starred messages to process')

    for index, starred in enumerate(starred_docs):
        snapshot = await _resolve_message_doc(starred.message_id, starred.channel_id, guild_id, starred.author_id, fallback_counts=fallback_counts)
        reply_snapshot = await _resolve_reply_snapshot(snapshot, guild_id)

        await _build_and_upsert_entry(starred, snapshot, reply_snapshot, guild_id=guild_id, now=now)
        migrated, skipped = await _migrate_reactions_for_entry(starred, cfg=cfg, guild_id=guild_id, now=now)
        total_reactions += migrated
        skipped_unweighted += skipped

        net, positive = await reaction_repo.aggregate_points(starred.message_id)
        await entry_repo.set_points(starred.message_id, net_points=net, positive_points=positive)

        if (index + 1) % 25 == 0:
            logger.info(f'convert: progress {index + 1}/{len(starred_docs)} entries (guild {guild_id})')

    stats = {
        'entries_processed': len(starred_docs),
        'reactions_migrated': total_reactions,
        'discord_fetched': fallback_counts['discord_fetched'],
        'placeholder': fallback_counts['placeholder'],
        'skipped_unweighted_emojis': skipped_unweighted,
        'skipped_no_config': 0,
    }
    logger.info(f'convert: done for guild {guild_id}: {stats}')

    if status_msg is not None:
        try:
            await status_msg.edit(content=(f'Done! Migrated {stats["entries_processed"]:,} entries with {stats["reactions_migrated"]:,} reactions; {stats["discord_fetched"]:,} fetched from discord, {stats["placeholder"]:,} placeholders, {stats["skipped_unweighted_emojis"]:,} skipped reactions on unweighted emojis'))
        except discord.HTTPException as err:
            logger.warning(f'convert: status edit failed: {err}')

    return stats
