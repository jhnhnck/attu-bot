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
from discord import Color, Embed, Message, RawBulkMessageDeleteEvent, RawMessageDeleteEvent, RawMessageUpdateEvent, Thread

from attubot import bot, config
from attubot.database.models import MessageDocument
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


def _theme_color() -> int:
    """Return bot theme color as int, falling back to blurple."""
    if config.theme:
        return int(config.theme.bot_color.lstrip('#'), 16)
    return Color.blurple().value


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


async def _build_attachments(message: Message, save_files: bool) -> list[dict]:
    """Serialize all attachments from a message.

    Downloads file contents only when save_files is True (i.e. lore/canon channels).
    """
    if not message.attachments:
        return []

    if save_files:
        tasks = [_save_attachment(a, message.id, message.guild.id, message.channel.id) for a in message.attachments]
        return list(await asyncio.gather(*tasks))

    return [
        {
            'filename': a.filename,
            'url': a.url,
            'content_type': a.content_type or '',
            'size': a.size,
            'saved_path': None,
        }
        for a in message.attachments
    ]


def _serialize_embeds(message: Message) -> list[dict]:
    """Convert message embeds to plain dicts for storage."""
    out = []
    for embed in message.embeds:
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
    """Return the author's global username - global_name if set, otherwise name."""
    return author.global_name or author.name


async def build_message_doc(message: Message) -> MessageDocument:
    """Build a MessageDocument from a pycord Message object."""
    guild_id = message.guild.id
    channel_id = message.channel.id

    # for thread messages, record the parent channel so queries and archive checks work correctly
    parent_channel_id: int | None = message.channel.parent_id if isinstance(message.channel, Thread) else None

    save_files = _is_archive_channel(channel_id, guild_id, parent_channel_id)
    attachments = await _build_attachments(message, save_files)
    embeds = _serialize_embeds(message)

    return MessageDocument(
        message_id=message.id,
        guild_id=guild_id,
        channel_id=channel_id,
        parent_channel_id=parent_channel_id,
        author_id=message.author.id,
        author_name=_global_username(message.author),
        author_bot=message.author.bot,
        content=message.content or '',
        attachments=attachments,
        embeds=embeds,
        sticker_ids=[s.id for s in message.stickers],
        reference_id=message.reference.message_id if message.reference else None,
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


async def _fetch_edit_context(payload: RawMessageUpdateEvent) -> _EditContext:
    """Look up stored record and return edit context; falls back to payload data on miss."""
    try:
        stored = await _get_repo().get(payload.message_id)
        logger.debug(f'log_edit: db lookup result - found={stored is not None}')
        if stored:
            logger.debug(f'log_edit: stored record - author={stored.author_name!r} author_id={stored.author_id} bot={stored.author_bot} content={stored.content!r}')
            return _EditContext(
                old_content=stored.content,
                author_name=stored.author_name,
                author_id=stored.author_id,
                author_bot=stored.author_bot,
            )
    except Exception as err:
        logger.warn(f'could not retrieve old message {payload.message_id} for edit log: {err}')

    # not in db - fall back to payload author info
    author_bot = payload.data.get('author', {}).get('bot', False)
    logger.debug(f'log_edit: no stored record - payload author.bot={author_bot}')
    return _EditContext(old_content=None, author_name=None, author_id=None, author_bot=author_bot)


def _build_edit_embed(ctx: _EditContext, payload: RawMessageUpdateEvent, new_content: str) -> Embed:
    """Build the edit log embed from context and payload."""
    embed = Embed(title='Message Edited', color=_theme_color())

    if ctx.author_name:
        embed.add_field(name='Author', value=f'<@{ctx.author_id}> ({ctx.author_name})', inline=True)

    embed.add_field(name='Channel', value=f'<#{payload.channel_id}>', inline=True)
    embed.add_field(
        name='Jump',
        value=f'[View Message](https://discord.com/channels/{payload.guild_id}/{payload.channel_id}/{payload.message_id})',
        inline=True,
    )

    if ctx.old_content is not None:
        embed.add_field(name='Before', value=_truncate(ctx.old_content) or '*(empty)*', inline=False)

    embed.add_field(name='After', value=_truncate(new_content) or '*(empty)*', inline=False)
    embed.set_footer(text=f'message id: {payload.message_id}')
    embed.timestamp = datetime.now(tz=UTC)
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

    embed = Embed(title='Message Deleted', color=Color.red().value)

    if stored:
        embed.add_field(name='Author', value=f'<@{stored.author_id}> ({stored.author_name})', inline=True)
    embed.add_field(name='Channel', value=f'<#{payload.channel_id}>', inline=True)

    if stored and stored.content:
        embed.add_field(name='Content', value=_truncate(stored.content), inline=False)

    if stored and stored.attachments:
        names = ', '.join(a.get('filename', '?') for a in stored.attachments)
        embed.add_field(name='Attachments', value=names, inline=False)

    embed.set_footer(text=f'message id: {payload.message_id}')
    embed.timestamp = datetime.now(tz=UTC)

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

    embed = Embed(title='Bulk Message Delete', color=Color.dark_red().value)
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

    embed.set_footer(text=f'guild: {payload.guild_id}')
    embed.timestamp = datetime.now(tz=UTC)

    try:
        await channel.send(embed=embed)
    except Exception as err:
        logger.error(f'failed to send bulk delete log in channel {payload.channel_id}: {err}')
