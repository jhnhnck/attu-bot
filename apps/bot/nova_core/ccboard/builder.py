# SPDX-License-Identifier: Apache-2.0
"""nova_core.ccboard.builder | rule-pipeline embed builder for ccboard posts."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

import discord
import structlog

from attu_models import BoardEntryDocument, MessageDocument
from nova_core.client.starboard import (
    _hydrate_stored_embed,
    _is_image,
    _parse_color,
    _should_merge_stored_embed,
)
from nova_core.client.util import format_message_link
from nova_core.config import GuildCCBoard


logger = structlog.stdlib.get_logger(__name__)


# color used for the "replying to" reply-context embed (discord dark background)
_REPLY_COLOR = 0x2B2D31

# tenor / giphy / etc. patterns where discord rewrites .gif into a .png proxy preview
_GIF_HOST_HINTS = ('tenor.com', 'giphy.com', 'gfycat.com')


# --- Pipeline State ---


@dataclass
class _State:
    """mutable state passed between pipeline rules"""

    main_embed: discord.Embed
    extra_embeds: list[discord.Embed] = field(default_factory=list)
    reply_embed: discord.Embed | None = None
    jump_url: str = ''
    color: int = 0
    image_attachments: list[dict] = field(default_factory=list)
    suppress_main: bool = False  # voice memo path replaces the main embed entirely


# --- Helpers ---


def _jump_url(snapshot: MessageDocument) -> str:
    return format_message_link(snapshot.guild_id, snapshot.channel_id, snapshot.message_id)


def _is_voice_attachment(attachment: dict) -> bool:
    """detect a discord voice memo attachment by content type"""
    ct = attachment.get('content_type', '')
    return ct.startswith('audio/')


def _looks_like_gif_embed(stored: dict) -> bool:
    """return True if the stored embed represents a gif/gifv link preview"""
    url = (stored.get('url') or '').lower()
    if any(host in url for host in _GIF_HOST_HINTS):
        return True
    image_url = (stored.get('image_url') or stored.get('video_url') or '').lower()
    return image_url.endswith('.gif') or image_url.endswith('.gifv')


def _resolve_gif_url(stored: dict) -> str | None:
    """prefer the actual gif/video url over the png preview proxy discord substitutes"""
    video = stored.get('video_url')
    if video:
        return video
    image = stored.get('image_url')
    if image and (image.lower().endswith('.gif') or image.lower().endswith('.gifv')):
        return image
    return image or video


# --- Rules ---


def rule_base(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """seed the main embed with author, timestamp, jump url, and color"""
    snapshot = entry.snapshot
    state.jump_url = _jump_url(snapshot)
    color_hex = config.positive_color if entry.net_points > 0 else config.negative_color
    state.color = _parse_color(color_hex)

    # avatar resolution mirrors the legacy starboard: prefer a live discord lookup
    # so the displayed avatar is current, fall back to None when the bot can't see the user
    avatar_url: str | None = None
    try:
        from nova_core.client.core import bot

        user = bot.get_user(snapshot.author.id)
        if user is not None:
            avatar_url = str(user.display_avatar)
    except Exception:
        # tests and pure-builder callers don't run inside a bot loop; degrade silently
        avatar_url = None

    main = discord.Embed(color=state.color)
    main.set_author(name=snapshot.author.name, url=state.jump_url, icon_url=avatar_url)
    main.timestamp = datetime.fromtimestamp(snapshot.created_at, tz=UTC)
    state.main_embed = main
    return state


def rule_reply_context(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """prepend a quoted-reply embed when the snapshot was a reply"""
    ref_doc = entry.reply_snapshot
    if ref_doc is None:
        return state

    ref_jump = _jump_url(ref_doc)
    avatar_url: str | None = None
    try:
        from nova_core.client.core import bot

        ref_user = bot.get_user(ref_doc.author.id)
        if ref_user is not None:
            avatar_url = str(ref_user.display_avatar)
    except Exception:
        avatar_url = None

    reply = discord.Embed(color=_REPLY_COLOR)
    reply.set_author(
        name=f'replying to {ref_doc.author.name}',
        url=ref_jump,
        icon_url=avatar_url,
    )
    if ref_doc.content.text:
        reply.description = ref_doc.content.text
    elif ref_doc.content.poll_text:
        reply.description = ref_doc.content.poll_text
    elif not ref_doc.content.attachments:
        first = ref_doc.content.embeds[0] if ref_doc.content.embeds else None
        reply.description = (first.get('title') or first.get('description') if first else None) or '*message has no text preview*'

    if ref_doc.content.attachments and ref_doc.content.attachments[0].get('url'):
        reply.set_image(url=ref_doc.content.attachments[0]['url'])

    state.reply_embed = reply
    return state


def rule_text_content(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """copy the snapshot text into the main embed description"""
    text = entry.snapshot.content.text
    if text:
        state.main_embed.description = text
    return state


def rule_primary_image(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """attach the first image attachment to the main embed.

    sets `main_embed.url = jump_url` so multi-image galleries render as a single
    connected unit on discord — the legacy starboard skipped this and the gallery
    rendered as disconnected blocks.
    """
    attachments = entry.snapshot.content.attachments
    state.image_attachments = [a for a in attachments if _is_image(a)]
    if not state.image_attachments:
        return state

    first = state.image_attachments[0]
    state.main_embed.set_image(url=first['url'])
    # gallery url-share fix: every embed in a multi-image gallery must share the same url
    state.main_embed.url = state.jump_url
    return state


def rule_extra_images(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """promote any additional image attachments into extra embeds.

    each extra embed must share `state.jump_url` so discord groups them into the
    same gallery as the main embed.
    """
    if len(state.image_attachments) <= 1:
        return state
    for att in state.image_attachments[1:]:
        extra = discord.Embed(color=state.color, url=state.jump_url)
        extra.set_image(url=att['url'])
        state.extra_embeds.append(extra)
    return state


def rule_link_previews(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """hydrate stored embed metadata.

    simple previews (description-only or image-only) merge into the main embed;
    richer ones (with title, fields, author, footer) become extra embeds.
    """
    stored_list = entry.snapshot.content.embeds
    if not stored_list:
        return state

    has_attachment_image = bool(state.image_attachments)
    main_text = state.main_embed.description
    main_has_image = bool(state.main_embed.image and state.main_embed.image.url)

    for stored in stored_list:
        # gif previews are handled in rule_gif so they pick up the gif url, not the png proxy
        if _looks_like_gif_embed(stored):
            continue
        if not main_text and not main_has_image and _should_merge_stored_embed(stored):
            # description-only merges land on the main embed
            if stored.get('description') and not state.main_embed.description:
                state.main_embed.description = stored['description']
                main_text = state.main_embed.description
            stored_image = stored.get('image_url') or stored.get('video_url') or stored.get('thumbnail_url')
            if stored_image and not has_attachment_image and not main_has_image:
                state.main_embed.set_image(url=stored_image)
                main_has_image = True
        else:
            state.extra_embeds.append(_hydrate_stored_embed(stored))
    return state


def rule_sticker(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """surface sticker-only messages using the cdn url as the image"""
    content = entry.snapshot.content
    if not content.sticker_urls:
        return state
    # only fire when there's no other media — text + sticker keeps the text
    if state.image_attachments or content.embeds:
        return state
    if not state.main_embed.image or not state.main_embed.image.url:
        state.main_embed.set_image(url=content.sticker_urls[0])
    if not content.text and not state.main_embed.description:
        state.main_embed.description = '*sticker*'
    return state


def rule_voice_memo(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """recognise voice memos and replace the empty preview with a notice"""
    attachments = entry.snapshot.content.attachments
    if not attachments:
        return state
    # voice memos arrive as a single audio attachment with no other media
    if len(attachments) != 1 or not _is_voice_attachment(attachments[0]):
        return state
    if state.image_attachments or entry.snapshot.content.text:
        return state
    state.main_embed.description = 'voice memo - playback unavailable'
    # voice memo has no useful image; clear any stale gallery state
    state.main_embed.set_image(url=None)
    state.main_embed.url = None
    return state


def rule_gif(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """hoist gif/gifv embeds to use the actual gif url instead of the png proxy"""
    stored_list = entry.snapshot.content.embeds
    for stored in stored_list:
        if not _looks_like_gif_embed(stored):
            continue
        gif_url = _resolve_gif_url(stored)
        if gif_url and (not state.main_embed.image or not state.main_embed.image.url):
            state.main_embed.set_image(url=gif_url)
            # share the jump url so any extra image embeds group into the same gallery
            state.main_embed.url = state.jump_url
            # one gif is enough; skip remaining gif embeds to avoid stacking previews
            break
    return state


def rule_forwarded(entry: BoardEntryDocument, config: GuildCCBoard, state: _State) -> _State:
    """tag forwarded messages with a footer marker"""
    if entry.snapshot.content.forwarded:
        state.main_embed.set_footer(text='forwarded message')
    return state


# --- Pipeline ---


_RULE = Callable[[BoardEntryDocument, GuildCCBoard, _State], _State]

_PIPELINE: tuple[_RULE, ...] = (
    rule_base,
    rule_reply_context,
    rule_text_content,
    rule_primary_image,
    rule_extra_images,
    rule_link_previews,
    rule_sticker,
    rule_voice_memo,
    rule_gif,
    rule_forwarded,
)


def build_embeds(entry: BoardEntryDocument, config: GuildCCBoard) -> list[discord.Embed]:
    """run the rule pipeline and return the full embed list for one ccboard entry.

    rules are pure: each takes (entry, config, state) and returns the updated state.
    the final list is `[reply_embed?, main_embed, *extra_embeds]`. all embeds in a
    multi-image gallery share `main_embed.url == jump_url` so discord groups them
    visually — this is the regression fix versus the legacy starboard.
    """
    state = _State(main_embed=discord.Embed())
    for rule in _PIPELINE:
        state = rule(entry, config, state)
    out: list[discord.Embed] = []
    if state.reply_embed is not None:
        out.append(state.reply_embed)
    out.append(state.main_embed)
    out.extend(state.extra_embeds)
    return out


logger.info('registered: ccboard builder')
