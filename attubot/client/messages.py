"""
AttuBot - Message Tracking
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from datetime import UTC, datetime
from typing import NamedTuple

import anyio
import discord
from discord import Color, Message, RawBulkMessageDeleteEvent, RawMessageDeleteEvent, RawMessageUpdateEvent, Thread

from attubot.client.core import bot, config
from attubot.client.embeds import make_embed
from attubot.database.models import MessageAuthor, MessageContent, MessageDocument, MessageRefs
from attubot.database.repositories import MessageRepository
from attubot.logging import get_logger


logger = get_logger(__name__)

# module-level singleton seeded by database/__init__.py
_message_repo: MessageRepository | None = None


def _get_repo() -> MessageRepository:
    if _message_repo is None:
        raise RuntimeError('message repo not initialized')
    return _message_repo


# --- Helpers ---


def _is_archive_channel(channel_id: int, guild_id: int, parent_channel_id: int | None = None) -> bool:
    """Return True if the channel (or its thread parent) is a lore or canon channel."""
    try:
        gc = config.guild(guild_id)
    except Exception:
        return False
    lore = gc.channels.lore_channels
    canon = gc.channels.canon_channels
    if channel_id in lore or channel_id in canon:
        return True
    # threads have a different id from their parent - check parent too
    return parent_channel_id is not None and (parent_channel_id in lore or parent_channel_id in canon)


def _backup_path() -> anyio.Path | None:
    """Return the configured backup root, or None if backups are disabled."""
    if config.backup and config.backup.path:
        return anyio.Path(config.backup.path)
    return None


async def _save_attachment(attachment: discord.Attachment, message_id: int, guild_id: int, channel_id: int) -> dict:
    """Download an attachment to disk and return a metadata dict.

    If download fails, falls back to URL-only entry.
    """
    base = _backup_path()
    meta: dict = {
        'filename': attachment.filename,
        'url': attachment.url,
        'content_type': attachment.content_type or '',
        'size': attachment.size,
        'saved_path': None,
    }

    if base is None:
        return meta

    dest_dir = base / 'attachments' / str(guild_id) / str(channel_id)
    await dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / f'{message_id}_{attachment.filename}'

    try:
        data = await attachment.read()
        await dest_file.write_bytes(data)
        # store relative to backup root so the path stays portable
        meta['saved_path'] = str(dest_file.relative_to(base))
        logger.debug(f'saved attachment: {meta["saved_path"]}')
    except Exception as err:
        logger.warn(f'failed to save attachment {attachment.filename} for message {message_id}: {err}')

    return meta


async def _build_attachments(
    attachments: list[discord.Attachment],
    message_id: int,
    guild_id: int,
    channel_id: int,
    save_files: bool,
) -> list[dict]:
    """Serialize a list of attachments.

    Downloads file contents only when save_files is True (i.e. lore/canon channels).
    """
    if not attachments:
        return []

    if save_files:
        tasks = [_save_attachment(a, message_id, guild_id, channel_id) for a in attachments]
        return list(await asyncio.gather(*tasks))

    return [
        {
            'filename': a.filename,
            'url': a.url,
            'content_type': a.content_type or '',
            'size': a.size,
            'saved_path': None,
        }
        for a in attachments
    ]


def _serialize_embeds(embeds: list[discord.Embed]) -> list[dict]:  # noqa: PLR0912 - embed serialization requires checking many optional fields
    """Convert a list of embeds to plain dicts for storage."""
    out = []
    for embed in embeds:
        d: dict = {}
        if embed.title:
            d['title'] = embed.title
        if embed.description:
            d['description'] = embed.description
        if embed.url:
            d['url'] = embed.url
        if embed.color:
            d['color'] = embed.color.value
        if embed.image:
            d['image_url'] = embed.image.url
        if embed.thumbnail:
            d['thumbnail_url'] = embed.thumbnail.url
        if embed.fields:
            d['fields'] = [{'name': f.name, 'value': f.value, 'inline': f.inline} for f in embed.fields]
        if embed.footer and embed.footer.text:
            d['footer_text'] = embed.footer.text
            if embed.footer.icon_url:
                d['footer_icon_url'] = embed.footer.icon_url
        if embed.author and embed.author.name:
            d['author_name'] = embed.author.name
            if embed.author.url:
                d['author_url'] = embed.author.url
            if embed.author.icon_url:
                d['author_icon_url'] = embed.author.icon_url
        if embed.timestamp:
            d['timestamp'] = embed.timestamp.isoformat()
        out.append(d)
    return out


def _is_public(message: Message) -> bool:
    """Return True if @everyone can read the channel this message is in."""
    guild = message.guild
    if guild is None:
        return False
    perms = message.channel.permissions_for(guild.default_role)
    return perms.read_messages


def _global_username(author: discord.User | discord.Member) -> str:
    """Return the author's global username"""
    return author.name


async def build_message_doc(message: Message) -> MessageDocument:
    """Build a MessageDocument from a pycord Message object."""
    guild_id = message.guild.id
    channel_id = message.channel.id

    # for thread messages, record the parent channel so queries and archive checks work correctly
    parent_channel_id: int | None = message.channel.parent_id if isinstance(message.channel, Thread) else None

    save_files = _is_archive_channel(channel_id, guild_id, parent_channel_id)

    # forwarded messages carry their content in snapshots, not on the message itself
    forwarded = False
    snapshot_msg = getattr(message.snapshots[0], 'message', None) if message.snapshots else None

    if snapshot_msg is not None:
        forwarded = True
        raw_text = snapshot_msg.content or ''
        raw_attachments = snapshot_msg.attachments
        raw_embeds = snapshot_msg.embeds
        raw_sticker_ids = [s.id for s in snapshot_msg.stickers]
    else:
        raw_text = message.content or ''
        raw_attachments = message.attachments
        raw_embeds = message.embeds
        raw_sticker_ids = [s.id for s in message.stickers]

    # never download snapshot attachments - original channel context is unavailable
    attachments = await _build_attachments(raw_attachments, message.id, guild_id, channel_id, save_files and not forwarded)
    embeds = _serialize_embeds(raw_embeds)

    return MessageDocument(
        message_id=message.id,
        guild_id=guild_id,
        channel_id=channel_id,
        parent_channel_id=parent_channel_id,
        author=MessageAuthor(
            id=message.author.id,
            name=_global_username(message.author),
            bot=message.author.bot,
        ),
        content=MessageContent(
            text=raw_text,
            attachments=attachments,
            embeds=embeds,
            sticker_ids=raw_sticker_ids,
            forwarded=forwarded,
        ),
        refs=MessageRefs(
            reply_to=message.reference.message_id if message.reference else None,
        ),
        pinned=message.pinned,
        public=_is_public(message),
        created_at=int(message.created_at.timestamp()),
        edited_at=int(message.edited_at.timestamp()) if message.edited_at else None,
    )


async def store_message(message: Message) -> None:
    """Persist a message to MongoDB. Called from on_message."""
    try:
        doc = await build_message_doc(message)
        await _get_repo().upsert(doc)
    except Exception as err:
        logger.error(f'failed to store message {message.id}: {err}')


# --- Log Embed Builders ---


def _truncate(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + '...'


async def _get_logs_channel(guild_id: int) -> discord.TextChannel | None:
    """Resolve the logs channel for a guild."""
    try:
        gc = config.guild(guild_id)
    except Exception:
        return None
    channel_id = gc.channels.logs
    if channel_id == 0:
        return None
    guild = bot.get_guild(guild_id)
    if guild is None:
        return None
    return guild.get_channel(channel_id)  # type: ignore[return-value]


class _EditContext(NamedTuple):
    old_content: str | None
    author_name: str | None
    author_id: int | None
    author_bot: bool
    author_avatar_url: str | None


def _resolve_avatar(guild_id: int, author_id: int) -> str | None:
    """look up a user's display avatar url from the bot's in-memory cache."""
    guild = bot.get_guild(guild_id)
    if guild:
        member = guild.get_member(author_id)
        if member and member.display_avatar:
            return member.display_avatar.url
    user = bot.get_user(author_id)
    if user and user.display_avatar:
        return user.display_avatar.url
    return None


async def _fetch_edit_context(payload: RawMessageUpdateEvent) -> _EditContext:
    """Look up stored record and return edit context; falls back to payload data on miss."""
    try:
        stored = await _get_repo().get(payload.message_id)
        logger.debug(f'log_edit: db lookup result - found={stored is not None}')
        if stored:
            logger.debug(f'log_edit: stored record - author={stored.author.name!r} author_id={stored.author.id} bot={stored.author.bot} content={stored.content.text!r}')
            avatar_url = _resolve_avatar(payload.guild_id, stored.author.id) if payload.guild_id else None
            return _EditContext(
                old_content=stored.content.text,
                author_name=stored.author.name,
                author_id=stored.author.id,
                author_bot=stored.author.bot,
                author_avatar_url=avatar_url,
            )
    except Exception as err:
        logger.warn(f'could not retrieve old message {payload.message_id} for edit log: {err}')

    # not in db - fall back to payload author info
    author_bot = payload.data.get('author', {}).get('bot', False)
    logger.debug(f'log_edit: no stored record - payload author.bot={author_bot}')
    return _EditContext(old_content=None, author_name=None, author_id=None, author_bot=author_bot, author_avatar_url=None)


def _build_edit_embed(ctx: _EditContext, payload: RawMessageUpdateEvent, new_content: str) -> discord.Embed:
    """Build the edit log embed from context and payload."""
    description = f'<@{ctx.author_id}> edited a message in <#{payload.channel_id}>' if ctx.author_id is not None else f'a message was edited in <#{payload.channel_id}>'

    embed = make_embed(
        'Message Edited',
        description=description,
        footer=f'message id: {payload.message_id}',
        author_name=ctx.author_name,
        author_icon_url=ctx.author_avatar_url,
    )

    embed.add_field(
        name='Jump',
        value=f'[View Message](https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id})',
        inline=True,
    )

    if ctx.old_content is not None:
        embed.add_field(name='Before', value=_truncate(ctx.old_content) or '*(empty)*', inline=False)

    embed.add_field(name='After', value=_truncate(new_content) or '*(empty)*', inline=False)
    return embed


async def log_edit(payload: RawMessageUpdateEvent) -> None:
    """Post a message-edited embed to the guild's logs channel."""
    if payload.guild_id is None:
        return

    now = int(datetime.now(tz=UTC).timestamp())

    logger.debug(f'log_edit: message_id={payload.message_id} guild_id={payload.guild_id} channel_id={payload.channel_id}')
    logger.debug(f'log_edit: full payload.data={payload.data!r}')

    # ignore events that aren't content changes (embed unfurls, pin toggles, etc.)
    if 'content' not in payload.data:
        logger.debug('log_edit: dropping - no content key in payload.data')
        return

    # drop non-edit updates where discord echoes the full message body (e.g. member timeout changes)
    if not payload.data.get('edited_timestamp'):
        logger.debug('log_edit: dropping - edited_timestamp is absent/null (not a content edit)')
        return

    new_content = payload.data['content']
    logger.debug(f'log_edit: new_content={new_content!r}')

    ctx = await _fetch_edit_context(payload)

    # skip if content didn't actually change
    if ctx.old_content is not None and new_content == ctx.old_content:
        logger.debug('log_edit: dropping - content unchanged')
        return

    # always update the stored record
    try:
        await _get_repo().mark_edited(payload.message_id, new_content, now)
        logger.debug(f'log_edit: marked message {payload.message_id} as edited in db')
    except Exception as err:
        logger.warn(f'failed to update edited message {payload.message_id}: {err}')

    # skip log embed for bot-authored messages
    if ctx.author_bot:
        logger.debug('log_edit: skipping log embed - message is bot-authored')
        return

    channel = await _get_logs_channel(payload.guild_id)
    logger.debug(f'log_edit: logs channel resolved - channel={channel}')
    if channel is None:
        logger.debug(f'log_edit: no logs channel for guild {payload.guild_id}, skipping embed')
        return

    embed = _build_edit_embed(ctx, payload, new_content)

    try:
        await channel.send(embed=embed)
    except Exception as err:
        logger.error(f'failed to send edit log for message {payload.message_id}: {err}')


async def log_delete(payload: RawMessageDeleteEvent) -> None:
    """Post a message-deleted embed to the guild's logs channel."""
    if payload.guild_id is None:
        return

    now = int(datetime.now(tz=UTC).timestamp())

    # always update the stored record, even if we can't post to logs
    stored = None
    try:
        stored = await _get_repo().get(payload.message_id)
        await _get_repo().mark_deleted(payload.message_id, now)
    except Exception as err:
        logger.warn(f'failed to mark message {payload.message_id} as deleted: {err}')

    channel = await _get_logs_channel(payload.guild_id)
    if channel is None:
        return

    description = f"<@{stored.author.id}>'s message was deleted in <#{payload.channel_id}>" if stored else f'a message was deleted in <#{payload.channel_id}>'

    avatar_url = _resolve_avatar(payload.guild_id, stored.author.id) if stored else None
    embed = make_embed(
        'Message Deleted',
        description=description,
        color=Color.red(),
        footer=f'message id: {payload.message_id}',
        author_name=stored.author.name if stored else None,
        author_icon_url=avatar_url,
    )

    if stored and stored.content.text:
        embed.add_field(name='Content', value=_truncate(stored.content.text), inline=False)

    if stored and stored.content.attachments:
        names = ', '.join(a.get('filename', '?') for a in stored.content.attachments)
        embed.add_field(name='Attachments', value=names, inline=False)

    try:
        await channel.send(embed=embed)
    except Exception as err:
        logger.error(f'failed to send delete log for message {payload.message_id}: {err}')


async def log_bulk_delete(payload: RawBulkMessageDeleteEvent) -> None:
    """Post a bulk-delete summary embed to the guild's logs channel."""
    if payload.guild_id is None:
        return

    channel = await _get_logs_channel(payload.guild_id)
    if channel is None:
        return

    now = int(datetime.now(tz=UTC).timestamp())

    ids = list(payload.message_ids)
    try:
        await _get_repo().mark_bulk_deleted(ids, now)
    except Exception as err:
        logger.warn(f'failed to bulk-delete {len(ids)} messages: {err}')

    embed = make_embed('Bulk Message Delete', color=Color.dark_red(), footer=f'guild: {payload.guild_id}')
    embed.add_field(name='Channel', value=f'<#{payload.channel_id}>', inline=True)
    embed.add_field(name='Count', value=str(len(ids)), inline=True)

    # list the first few cached messages to give context
    if payload.cached_messages:
        lines = []
        for msg in list(payload.cached_messages)[:5]:
            preview = (msg.content[:60] + '...') if len(msg.content) > 60 else msg.content
            lines.append(f'<@{msg.author.id}>: {preview or "*(no text)*"}')
        if len(payload.cached_messages) > 5:
            lines.append(f'...and {len(payload.cached_messages) - 5} more')
        embed.add_field(name='Preview', value='\n'.join(lines), inline=False)

    try:
        await channel.send(embed=embed)
    except Exception as err:
        logger.error(f'failed to send bulk delete log in channel {payload.channel_id}: {err}')
