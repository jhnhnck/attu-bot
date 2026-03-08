"""
AttuBot - Starboard Logic
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
import re
from datetime import UTC, datetime
from pathlib import Path

import discord

from attubot.database.models import MessageDocument, StarredMessageDocument
from attubot.database.repositories import StarboardRepository
from attubot.logging import get_logger


logger = get_logger(__name__)

# module-level singleton seeded by database/__init__.py
_starboard_repo: StarboardRepository | None = None

# per-message locks to prevent concurrent creation of duplicate starboard posts
_post_creation_locks: dict[int, asyncio.Lock] = {}

_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.apng'}

# regex to extract per-emoji counts and the jump url from a starboard content string
# e.g. "⭐ **4** | 🌟 **1** | https://discord.com/channels/g/c/m"
_REACTION_PART_RE = re.compile(r'(.+?)\s+\*\*(\d+)\*\*')
_JUMP_URL_RE = re.compile(r'https://discord\.com/channels/(\d+)/(\d+)/(\d+)')

# color used for the "replying to" embed (discord dark background)
_REPLY_COLOR = 0x2B2D31


def _get_repo() -> StarboardRepository:
    if _starboard_repo is None:
        raise RuntimeError('starboard repo not initialized')
    return _starboard_repo


# --- Helpers ---


def _parse_color(hex_str: str) -> int:
    """convert '#RRGGBB' hex string to int"""
    return int(hex_str.lstrip('#'), 16)


def _strip_query(url: str) -> str:
    return url.split('?', 1)[0]


def _looks_like_image_url(url: str) -> bool:
    if not url:
        return False
    path = _strip_query(url)
    ext = Path(path.lower()).suffix
    return ext in _IMAGE_EXTENSIONS


def _should_merge_stored_embed(stored: dict) -> bool:
    if not stored.get('description'):
        return False
    if stored.get('title') or stored.get('fields') or stored.get('author_name') or stored.get('footer_text'):  # noqa: SIM103 - multi-condition early return is more readable than a negated compound expression
        return False
    return True


def _merge_stored_embed(embed: discord.Embed, stored: dict, has_attachment_image: bool) -> None:
    if stored.get('description') and not embed.description:
        embed.description = stored['description']
    if stored.get('title'):
        embed.title = stored['title']
    if stored.get('url'):
        embed.url = stored['url']
    image_url = stored.get('image_url') or stored.get('thumbnail_url')
    if image_url and not has_attachment_image:
        embed.set_image(url=image_url)
    for field in stored.get('fields', []):
        embed.add_field(name=field['name'], value=field['value'], inline=field.get('inline', False))


def _hydrate_stored_embed(stored: dict) -> discord.Embed:
    color = stored.get('color')
    embed = discord.Embed(color=color if color is not None else discord.Embed.Empty)
    if stored.get('title'):
        embed.title = stored['title']
    if stored.get('description'):
        embed.description = stored['description']
    if stored.get('url'):
        embed.url = stored['url']
    image_url = stored.get('image_url') or stored.get('thumbnail_url')
    if image_url:
        embed.set_image(url=image_url)
    if stored.get('fields'):
        for field in stored['fields']:
            embed.add_field(name=field['name'], value=field['value'], inline=field.get('inline', False))
    if stored.get('footer_text'):
        embed.set_footer(text=stored['footer_text'], icon_url=stored.get('footer_icon_url'))
    if stored.get('author_name'):
        embed.set_author(
            name=stored['author_name'],
            url=stored.get('author_url'),
            icon_url=stored.get('author_icon_url'),
        )
    timestamp = stored.get('timestamp')
    if timestamp:
        try:  # noqa: SIM105 - inline try/except is clearer than contextlib.suppress for a single-line value assignment
            embed.timestamp = datetime.fromisoformat(timestamp)
        except ValueError:
            pass
    return embed


def _weighted_count(emoji: str, reactions: dict[str, list[int]], super_reactions: dict[str, list[int]]) -> float:
    """return the weighted reaction count for one emoji: normal = 1.0, super = 1.5"""
    return len(reactions.get(emoji, [])) + len(super_reactions.get(emoji, [])) * 1.5


def _fmt_count(value: float) -> str:
    """format a weighted count - omit decimal if it's a whole number"""
    return str(int(value)) if value == int(value) else str(value)


def dominant_color(
    reactions: dict[str, list[int]],
    emoji_colors: dict[str, str],
    fallback: int | None = None,
    super_reactions: dict[str, list[int]] | None = None,
) -> int:
    """return the color for the emoji with the highest weighted reaction count"""
    from attubot.util import theme_color

    super_reactions = super_reactions or {}
    configured = {e for e in emoji_colors if (reactions.get(e) or super_reactions.get(e))}
    if not configured:
        return fallback if fallback is not None else theme_color()
    best = max(configured, key=lambda e: _weighted_count(e, reactions, super_reactions))
    return _parse_color(emoji_colors[best])


def build_content(
    reactions: dict[str, list[int]],
    jump_url: str,
    emoji_colors: dict[str, str],
    super_reactions: dict[str, list[int]] | None = None,
) -> str:
    """build the starboard message content string - e.g. '⭐ **4** | 🌟 **1.5** | https://...'"""
    super_reactions = super_reactions or {}
    parts = []
    # all configured emojis with any reaction (normal or super), sorted by weighted count desc
    active = {e for e in emoji_colors if (reactions.get(e) or super_reactions.get(e))}
    for emoji in sorted(active, key=lambda e: -_weighted_count(e, reactions, super_reactions)):
        wc = _weighted_count(emoji, reactions, super_reactions)
        parts.append(f'{emoji} **{_fmt_count(wc)}**')
    parts.append(jump_url)
    return ' | '.join(parts)


def parse_starboard_content(content: str) -> tuple[dict[str, int], str | None]:
    """parse a legacy starboard content string into (emoji_counts, jump_url).

    returns ({emoji: count}, jump_url) where jump_url may be None if not found.
    splits on ' | ' first so emoji names are never contaminated by the separator.
    """
    url_match = _JUMP_URL_RE.search(content)
    jump_url = url_match.group(0) if url_match else None

    pre = content[: url_match.start()] if url_match else content

    emoji_counts: dict[str, int] = {}
    for segment in pre.split(' | '):
        stripped = segment.strip()
        m = _REACTION_PART_RE.match(stripped)
        if m:
            emoji = m.group(1).strip()
            count = int(m.group(2))
            if emoji:
                emoji_counts[emoji] = count

    return emoji_counts, jump_url


def parse_jump_url(url: str) -> tuple[int, int, int] | None:
    """extract (guild_id, channel_id, message_id) from a discord jump url, or None"""
    m = _JUMP_URL_RE.match(url)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))
    return None


# --- Embed Builder ---


async def build_embeds(
    message_doc: 'MessageDocument',
    guild_id: int,
    color: int,
) -> list[discord.Embed]:
    """build the list of Discord embeds that reproduce the original message in the starboard.

    handles: standard text, images (single and multiple), replies, and stored link preview embeds.
    """
    from attubot import bot
    from attubot.messages import _get_repo as _get_msg_repo

    jump_url = f'https://discord.com/channels/{guild_id}/{message_doc.channel_id}/{message_doc.message_id}'

    # resolve author avatar
    user = bot.get_user(message_doc.author.id)
    avatar_url: str | None = str(user.display_avatar) if user else None

    embeds: list[discord.Embed] = []

    # --- reply context embed ---
    if message_doc.refs.reply_to:
        try:
            ref_doc = await _get_msg_repo().get(message_doc.refs.reply_to)
        except Exception:
            ref_doc = None

        if ref_doc:
            ref_jump = f'https://discord.com/channels/{guild_id}/{ref_doc.channel_id}/{ref_doc.message_id}'
            ref_user = bot.get_user(ref_doc.author.id)
            ref_avatar: str | None = str(ref_user.display_avatar) if ref_user else None

            reply_embed = discord.Embed(color=_REPLY_COLOR)
            reply_embed.set_author(
                name=f'Replying to {ref_doc.author.name}',
                url=ref_jump,
                icon_url=ref_avatar,
            )
            if ref_doc.content.text:
                reply_embed.description = ref_doc.content.text
            # show first image attachment from the referenced message
            if ref_doc.content.attachments and ref_doc.content.attachments[0].get('url'):
                reply_embed.set_image(url=ref_doc.content.attachments[0]['url'])
            embeds.append(reply_embed)

    # --- main embed ---
    main_embed = discord.Embed(color=color)
    main_embed.set_author(name=message_doc.author.name, url=jump_url, icon_url=avatar_url)
    main_embed.timestamp = datetime.fromtimestamp(message_doc.created_at, tz=UTC)

    if message_doc.content.text:
        main_embed.description = message_doc.content.text

    image_attachments = [a for a in message_doc.content.attachments if _is_image(a)]
    if image_attachments:
        main_embed.set_image(url=image_attachments[0]['url'])

    hydrated_embed: discord.Embed | None = None
    if message_doc.content.embeds:
        stored = message_doc.content.embeds[0]
        if not message_doc.content.text and _should_merge_stored_embed(stored):
            _merge_stored_embed(main_embed, stored, has_attachment_image=bool(image_attachments))
        else:
            hydrated_embed = _hydrate_stored_embed(stored)

    embeds.append(main_embed)
    if hydrated_embed is not None:
        embeds.append(hydrated_embed)

    # --- extra image attachments as separate embeds ---
    for att in image_attachments[1:]:
        extra = discord.Embed(color=color)
        extra.set_image(url=att['url'])
        embeds.append(extra)

    return embeds


def _is_image(attachment: dict) -> bool:
    """return True if the attachment is an image or otherwise looks like one"""
    url = attachment.get('url')
    if not url:
        return False
    ct = attachment.get('content_type', '')
    if ct.startswith('image/'):
        return True
    return _looks_like_image_url(url)


# --- Reaction Processing ---


async def _fetch_store_and_backfill(
    guild_id: int,
    channel_id: int,
    message_id: int,
    sb,
    skip_user: int,
    skip_emoji: str,
) -> 'MessageDocument | None':
    """fetch a missing message from discord, store it, then backfill any existing star reactions.

    skips (skip_user, skip_emoji) since the caller will process that combination.
    returns the stored MessageDocument or None on failure.
    """
    from attubot import bot
    from attubot.messages import _get_repo as _get_msg_repo
    from attubot.messages import build_message_doc

    try:
        channel = bot.get_channel(channel_id)
        if channel is None:
            channel = await bot.fetch_channel(channel_id)
        discord_msg = await channel.fetch_message(message_id)
    except Exception as err:
        logger.warn(f'starboard: could not fetch message {message_id} from channel {channel_id}: {err}')
        return None

    try:
        doc = await build_message_doc(discord_msg)
        await _get_msg_repo().upsert(doc)
        logger.info(f'starboard: stored missing message {message_id}')
    except Exception as err:
        logger.warn(f'starboard: could not store fetched message {message_id}: {err}')
        return None

    # backfill any existing star reactions, excluding the one the caller is about to process
    repo = _get_repo()
    backfilled = 0
    for reaction in discord_msg.reactions:
        emoji = str(reaction.emoji)
        if emoji not in sb.emojis:
            continue
        async for user in reaction.users():
            if user.id == doc.author.id or user.bot:
                continue
            if user.id == skip_user and emoji == skip_emoji:
                continue
            if await repo.get(message_id) is None:
                existing_doc = StarredMessageDocument(
                    message_id=message_id,
                    channel_id=doc.channel_id,
                    guild_id=guild_id,
                    author_id=doc.author.id,
                )
                await repo.upsert(existing_doc)
            await repo.add_reaction(message_id, emoji, user.id)
            logger.info(f'starboard: backfilled {emoji} from user {user.id} on message {message_id}')
            backfilled += 1

    if backfilled:
        logger.info(f'starboard: backfilled {backfilled} existing reaction(s) on message {message_id}')

    return doc


async def backfill_message_reactions(message: discord.Message, guild_id: int) -> None:  # noqa: PLR0912 - inherently branchy starboard backfill handler
    """process all existing reactions on a discord message for starboard backfill.

    intended to be called during channel backfill for messages we hadn't seen before.
    no-ops on the starboard channel itself, bot messages, or unconfigured emojis.
    """
    from attubot import config
    from attubot.messages import _get_repo as _get_msg_repo

    try:
        guild_config = config.guild(guild_id)
    except Exception:
        return

    sb = guild_config.starboard
    if not sb.channel_id or not sb.emojis:
        return

    # don't process reactions on the starboard channel itself
    if message.channel.id == sb.channel_id:
        return

    if message.author.bot:
        return

    configured = {str(r.emoji): r for r in message.reactions if str(r.emoji) in sb.emojis}
    if not configured:
        return

    repo = _get_repo()
    msg_repo = _get_msg_repo()

    # collect per-emoji user sets, excluding self-stars and bots
    new_reactions: dict[str, list[int]] = {}
    for emoji, reaction in configured.items():
        users = []
        async for user in reaction.users():
            if user.id != message.author.id and not user.bot:
                users.append(user.id)
        if users:
            new_reactions[emoji] = users

    if not new_reactions:
        return

    existing = await repo.get(message.id)
    if existing is None:
        msg_doc = await msg_repo.get(message.id)
        author_id = msg_doc.author.id if msg_doc else message.author.id
        total_new = sum(len(v) for v in new_reactions.values())
        doc = StarredMessageDocument(
            message_id=message.id,
            channel_id=message.channel.id,
            guild_id=guild_id,
            author_id=author_id,
            reactions=new_reactions,
            total_reactions=total_new,
            weighted_total=float(total_new),  # backfill only counts normal reactions
        )
        await repo.upsert(doc)
    else:
        # merge into existing, deduplicating per user per emoji
        merged = {k: list(v) for k, v in existing.reactions.items()}
        for emoji, users in new_reactions.items():
            current = set(merged.get(emoji, []))
            current.update(users)
            merged[emoji] = list(current)
        total_normal = sum(len(v) for v in merged.values())
        total_super = sum(len(v) for v in existing.super_reactions.values())
        doc = StarredMessageDocument(
            message_id=existing.message_id,
            channel_id=existing.channel_id,
            guild_id=existing.guild_id,
            author_id=existing.author_id,
            starboard_message_id=existing.starboard_message_id,
            reactions=merged,
            super_reactions=existing.super_reactions,
            total_reactions=total_normal + total_super,
            weighted_total=float(total_normal) + float(total_super) * 1.5,
        )
        await repo.upsert(doc)

    total_new = sum(len(v) for v in new_reactions.values())
    logger.info(f'starboard: backfilled {total_new} reaction(s) on message {message.id} during channel scan')

    updated = await repo.get(message.id)
    if updated:
        await _sync_starboard_post(guild_id, updated, guild_config)


async def handle_star_add(  # noqa: PLR0911, PLR0912, PLR0915 - inherently branchy star event handler with many early-exit guard conditions
    guild_id: int,
    channel_id: int,
    message_id: int,
    user_id: int,
    emoji_str: str,
    is_burst: bool = False,
) -> None:
    """process a new star reaction on either an original message or a starboard message.

    creates the starboard document if needed, then posts or updates the starboard entry.
    super reactions (is_burst=True) count as 1.5 stars; a user can only have one type per emoji.
    """
    from attubot import config
    from attubot.messages import _get_repo as _get_msg_repo

    try:
        guild_config = config.guild(guild_id)
    except Exception:
        return

    sb = guild_config.starboard
    if not sb.channel_id:
        logger.debug(f'starboard: no channel configured for guild {guild_id}, ignoring reaction')
        return
    if emoji_str not in sb.emojis:
        logger.debug(f'starboard: emoji {emoji_str!r} not in configured emojis {list(sb.emojis)!r}, ignoring')
        return

    # skip our own bot's reactions and any configured legacy bot IDs
    from attubot import bot as _bot

    if _bot.user and user_id == _bot.user.id:
        logger.debug(f'starboard: ignoring own bot reaction from {user_id}')
        return
    if user_id in sb.valid_bots:
        logger.debug(f'starboard: ignoring valid_bot reaction from {user_id}')
        return

    repo = _get_repo()
    msg_repo = _get_msg_repo()

    stored_doc = await msg_repo.get(message_id)
    if isinstance(stored_doc, MessageDocument) and stored_doc.refs.starboard_post:
        message_id = stored_doc.refs.starboard_post
        stored_doc = await msg_repo.get(message_id)  # may return None if not cached

    real_channel_id = stored_doc.channel_id if stored_doc else channel_id
    if stored_doc is None:
        existing_star_doc = await repo.get(message_id)
        if existing_star_doc:
            real_channel_id = existing_star_doc.channel_id

    # determine if the reaction is on a starboard post or a regular message in the starboard channel
    real_message_id = message_id
    if channel_id == sb.channel_id:
        existing = await repo.get_by_starboard_message(message_id)
        if existing is not None:
            # reaction is on a known starboard post - redirect to the original
            real_message_id = existing.message_id
            real_channel_id = existing.channel_id
        # else: regular message posted in the starboard channel - fall through and treat normally

    # fetch the original message to validate self-star and get author info
    msg_doc = await _get_msg_repo().get(real_message_id)
    if msg_doc is None:
        logger.debug(f'starboard: message {real_message_id} not in db, attempting fetch and store')
        msg_doc = await _fetch_store_and_backfill(guild_id, real_channel_id, real_message_id, sb, skip_user=user_id, skip_emoji=emoji_str)
        if msg_doc is None:
            return

    # self-stars don't count
    if user_id == msg_doc.author.id:
        logger.debug(f'starboard: ignoring self-star from {user_id} on message {real_message_id}')
        return

    # create the starboard document if this is the first star
    if await repo.get(real_message_id) is None:
        doc = StarredMessageDocument(
            message_id=real_message_id,
            channel_id=msg_doc.channel_id,
            guild_id=guild_id,
            author_id=msg_doc.author.id,
        )
        await repo.upsert(doc)

    # add the reaction - super reactions take priority and remove any existing normal reaction
    if is_burst:
        updated = await repo.add_super_reaction(real_message_id, emoji_str, user_id)
        reaction_kind = 'super'
    else:
        updated = await repo.add_reaction(real_message_id, emoji_str, user_id)
        reaction_kind = 'normal'
    if updated is None:
        return

    logger.info(f'starboard: {emoji_str} ({reaction_kind}) from user {user_id} on message {real_message_id} - weighted total now {updated.weighted_total}')

    await _sync_starboard_post(guild_id, updated, guild_config)


async def handle_star_remove(
    guild_id: int,
    channel_id: int,
    message_id: int,
    user_id: int,
    emoji_str: str,
    is_burst: bool = False,
) -> None:
    """process a star removal; updates the starboard post if it exists."""
    from attubot import config
    from attubot.messages import _get_repo as _get_msg_repo

    try:
        guild_config = config.guild(guild_id)
    except Exception:
        return

    sb = guild_config.starboard
    if not sb.channel_id or emoji_str not in sb.emojis:
        return

    repo = _get_repo()
    msg_repo = _get_msg_repo()

    stored_doc = await msg_repo.get(message_id)
    if isinstance(stored_doc, MessageDocument) and stored_doc.refs.starboard_post:
        message_id = stored_doc.refs.starboard_post

    real_message_id = message_id
    if channel_id == sb.channel_id:
        existing = await repo.get_by_starboard_message(message_id)
        if existing is None:
            return
        real_message_id = existing.message_id

    if is_burst:
        updated = await repo.remove_super_reaction(real_message_id, emoji_str, user_id)
    else:
        updated = await repo.remove_reaction(real_message_id, emoji_str, user_id)
    if updated is None:
        return

    logger.info(f'starboard: {emoji_str} removed by user {user_id} on message {real_message_id} - weighted total now {updated.weighted_total}')

    await _sync_starboard_post(guild_id, updated, guild_config)


async def _sync_starboard_post(guild_id: int, doc: StarredMessageDocument, guild_config) -> None:  # noqa: PLR0912, PLR0915 - branchy post create/update/replace logic with multiple discord error cases
    """create or update (or do nothing for) the starboard channel post for a starred message."""
    from attubot import bot
    from attubot.messages import _get_repo as _get_msg_repo

    sb = guild_config.starboard
    repo = _get_repo()

    channel = bot.get_channel(sb.channel_id)
    if channel is None:
        logger.warn(f'starboard: channel {sb.channel_id} not in cache for guild {guild_id}')
        return

    msg_doc = await _get_msg_repo().get(doc.message_id)
    if msg_doc is None:
        logger.warn(f'starboard: original message {doc.message_id} not found in db')
        return

    jump_url = f'https://discord.com/channels/{guild_id}/{msg_doc.channel_id}/{msg_doc.message_id}'
    content = build_content(doc.reactions, jump_url, sb.emojis, super_reactions=doc.super_reactions)
    color = dominant_color(doc.reactions, sb.emojis, super_reactions=doc.super_reactions)
    embeds = await build_embeds(msg_doc, guild_id, color)

    if doc.starboard_message_id is None:
        lock = _post_creation_locks.setdefault(doc.message_id, asyncio.Lock())
        async with lock:
            # re-fetch inside the lock; a concurrent call may have already created the post
            fresh = await repo.get(doc.message_id)
            if fresh is None:
                return
            if fresh.starboard_message_id is None:
                # still no post - we are responsible for creating it
                if fresh.weighted_total < 2:
                    return
                try:
                    sb_msg = await channel.send(content=content, embeds=embeds)
                    await repo.set_starboard_message(fresh.message_id, sb_msg.id)
                    # bot reacts to its own starboard post with all active emojis
                    for emoji in fresh.reactions:
                        if fresh.reactions[emoji] and emoji in sb.emojis:
                            try:
                                await sb_msg.add_reaction(emoji)
                            except Exception as err:
                                logger.warn(f'starboard: failed to add reaction {emoji} to post: {err}')
                    logger.info(f'starboard: created post {sb_msg.id} for message {fresh.message_id} ({fresh.total_reactions} reactions)')
                except Exception as err:
                    logger.error(f'starboard: failed to create post for message {fresh.message_id}: {err}')
                return
            # concurrent call already created the post - fall through to update it
            doc = fresh

    # update existing post
    try:
        sb_msg = await channel.fetch_message(doc.starboard_message_id)
        await sb_msg.edit(content=content, embeds=embeds)
        logger.debug(f'starboard: updated post {doc.starboard_message_id} ({doc.total_reactions} reactions)')
    except discord.NotFound:
        # old post was deleted - clear the reference so we can create a new one
        logger.warn(f'starboard: post {doc.starboard_message_id} not found, clearing reference')
        await repo.set_starboard_message(doc.message_id, None)
    except discord.Forbidden:
        # not our message (old bot) - send a reply to the old post so it's easy to jump to
        logger.warn(f'starboard: cannot edit post {doc.starboard_message_id} (not our message), sending reply')
        try:
            try:
                old_msg = await channel.fetch_message(doc.starboard_message_id)
                new_msg = await channel.send(content=content, embeds=embeds, reference=old_msg)
            except discord.NotFound:
                new_msg = await channel.send(content=content, embeds=embeds)
            await repo.set_starboard_message(doc.message_id, new_msg.id)
            for emoji in doc.reactions:
                if doc.reactions[emoji] and emoji in sb.emojis:
                    try:
                        await new_msg.add_reaction(emoji)
                    except Exception as react_err:
                        logger.warn(f'starboard: failed to add reaction {emoji} to replacement post: {react_err}')
            logger.info(f'starboard: replaced uneditable post {doc.starboard_message_id} with {new_msg.id} for message {doc.message_id}')
        except Exception as err:
            logger.error(f'starboard: failed to send replacement for post {doc.starboard_message_id}: {err}')
    except Exception as err:
        logger.error(f'starboard: failed to update post {doc.starboard_message_id}: {err}')


logger.info('Registered: starboard module')
