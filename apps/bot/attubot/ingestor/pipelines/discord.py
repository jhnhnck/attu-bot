"""
AttuBot - Discord Message Ingestion Pipeline
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time
import uuid

from attubot.client.calendar import haracalnde_date
from attubot.client.core import config
from attubot.database.models import ChatCharacterDocument, ChatSourceDocument, MessageDocument
from attubot.database.repositories import ChatCharacterRepository, MessageRepository
from attubot.ingestor.embedder import _get_embedder
from attubot.ingestor.registry import get_source, upsert_source
from attubot.ingestor.summarizer import _get_summarizer
from attubot.ingestor.vector_store import _get_vector_store
from attubot.logging import get_logger


logger = get_logger(__name__)

_DISCORD_COLLECTION = 'discord'

_msg_repo: 'MessageRepository | None' = None
_char_repo: 'ChatCharacterRepository | None' = None


def _get_msg_repo() -> 'MessageRepository':
    global _msg_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _msg_repo is None:
        from attubot import db

        _msg_repo = MessageRepository(db.get_db())
    return _msg_repo


def _get_char_repo() -> 'ChatCharacterRepository':
    global _char_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _char_repo is None:
        from attubot import db

        _char_repo = ChatCharacterRepository(db.get_db())
    return _char_repo


# --- pure functions (no I/O; fully unit-testable) ---


def token_count(text: str) -> int:
    """approximate token count by splitting on whitespace"""
    return len(text.split())


def filter_noise(
    messages: list[MessageDocument],
    min_tokens: int,
    ignored_user_ids: list[int],
) -> list[MessageDocument]:
    """return messages that pass the ingestion noise filter.
    filtered messages may still appear in context expansion - this is ingestion-only."""
    result = []
    for m in messages:
        if m.author.id in ignored_user_ids:
            continue
        if m.author.bot:
            continue
        if token_count(m.content.text) < min_tokens:
            continue
        result.append(m)
    return result


def build_reply_chains(
    messages: list[MessageDocument],
) -> tuple[list[list[MessageDocument]], list[MessageDocument]]:
    """traverse refs.reply_to to group messages into reply chains.
    returns (chains, remaining) where remaining messages are not part of any chain."""
    by_id: dict[int, MessageDocument] = {m.message_id: m for m in messages}
    in_chain: set[int] = set()
    chains: list[list[MessageDocument]] = []

    # find all messages that are the root of a reply chain (replied to but not themselves replies)
    for m in messages:
        if m.refs.reply_to is not None and m.refs.reply_to not in by_id:
            # reply to a message outside the window; treat as standalone
            continue

    # build chains by finding connected components via reply_to
    visited: set[int] = set()
    for m in messages:
        if m.message_id in visited:
            continue
        if m.refs.reply_to is None:
            continue
        # this message is a reply; walk the chain
        chain: list[int] = []
        current = m
        while current is not None:
            if current.message_id in visited:
                # merge into existing chain if possible
                break
            chain.append(current.message_id)
            visited.add(current.message_id)
            parent_id = current.refs.reply_to
            current = by_id.get(parent_id) if parent_id is not None else None

        if len(chain) > 1:
            # sort chain chronologically
            chain_msgs = sorted([by_id[mid] for mid in chain], key=lambda x: x.created_at)
            chains.append(chain_msgs)
            in_chain.update(chain)

    remaining = [m for m in messages if m.message_id not in in_chain]
    return chains, remaining


def group_by_time_window(
    messages: list[MessageDocument],
    window_minutes: int,
) -> list[list[MessageDocument]]:
    """bucket messages into time windows by created_at per channel.
    messages must be sorted by created_at ascending."""
    if not messages:
        return []

    window_seconds = window_minutes * 60
    windows: list[list[MessageDocument]] = []
    current_window: list[MessageDocument] = []
    window_start: int | None = None
    current_channel: int | None = None

    for m in sorted(messages, key=lambda x: (x.channel_id, x.created_at)):
        if current_channel != m.channel_id:
            # new channel; flush and start fresh
            if current_window:
                windows.append(current_window)
            current_window = [m]
            window_start = m.created_at
            current_channel = m.channel_id
        elif window_start is not None and (m.created_at - window_start) >= window_seconds:
            # time gap exceeded; start a new window
            windows.append(current_window)
            current_window = [m]
            window_start = m.created_at
        else:
            current_window.append(m)

    if current_window:
        windows.append(current_window)

    return windows


# --- pipeline class ---


class DiscordPipeline:
    """fetches discord messages, groups into windows, summarizes, and upserts into qdrant"""

    async def run(self) -> None:
        """main pipeline entry point - called by DiscordIngestTask every 5 minutes"""
        cfg = config.chat_runtime
        channel_map = cfg.chat_channels  # str(channel_id) -> ChatChannelConfig

        active_channels = {int(cid): ch_cfg for cid, ch_cfg in channel_map.items() if ch_cfg.ingest}
        if not active_channels:
            logger.debug('no active discord channels configured; skipping discord ingest')
            return

        since_timestamp = int(time.time()) - cfg.discord_lookback_hours * 3600
        channel_ids = list(active_channels.keys())

        # build character roster text for summarization prompts
        characters = await _get_char_repo().get_all()
        roster_text = _format_character_roster(cfg.user_nations, characters)

        # fetch messages across all authorized guilds
        all_messages: list[MessageDocument] = []
        for guild_id in config.authorized_guilds:
            msgs = await _get_msg_repo().get_in_channels_since(guild_id, channel_ids, since_timestamp)
            all_messages.extend(msgs)

        if not all_messages:
            logger.debug('no new discord messages found in lookback window')
            return

        logger.debug(f'discord pipeline: {len(all_messages)} messages from {len(channel_ids)} channels')

        store = _get_vector_store()
        embedder = _get_embedder()
        await store.ensure_collection(_DISCORD_COLLECTION, embedder.dim)

        # process per channel
        by_channel: dict[int, list[MessageDocument]] = {}
        for m in all_messages:
            effective_id = m.channel_id
            by_channel.setdefault(effective_id, []).append(m)

        for channel_id, channel_msgs in by_channel.items():
            ch_cfg = active_channels.get(channel_id)
            if ch_cfg is None:
                # thread in an active channel; use parent's config
                parent_id = channel_msgs[0].parent_channel_id
                ch_cfg = active_channels.get(parent_id) if parent_id is not None else None
            if ch_cfg is None:
                continue

            chains, remaining = build_reply_chains(channel_msgs)
            time_windows = group_by_time_window(remaining, cfg.discord_window_minutes)
            all_windows = chains + time_windows

            for window in all_windows:
                await self._process_window(window, channel_id, ch_cfg, roster_text, cfg)

    async def _process_window(self, window, channel_id, ch_cfg, roster_text, cfg) -> None:
        """summarize a single message window and upsert to qdrant + chat_sources"""
        from qdrant_client.models import PointStruct

        filtered = filter_noise(window, cfg.noise_filter_min_tokens, cfg.ignored_user_ids)
        if not filtered:
            return

        min_id = min(m.message_id for m in filtered)
        max_id = max(m.message_id for m in filtered)
        source_id = f'discord_{channel_id}_{min_id}_{max_id}'

        # skip if already ingested
        existing = await get_source(source_id)
        if existing and not existing.flagged_incorrect:
            return

        # determine content_type: meeting_scene if thread in a roleplay channel
        parent_id = filtered[0].parent_channel_id
        is_thread = parent_id is not None
        parent_cfg = config.chat_runtime.chat_channels.get(str(parent_id)) if is_thread else None
        is_roleplay_thread = is_thread and parent_cfg is not None and parent_cfg.channel_type == 'roleplay'
        content_type = 'meeting_scene' if is_roleplay_thread else 'discord_window'

        # build pc date range
        ts_start = filtered[0].created_at
        ts_end = filtered[-1].created_at
        date_start_pc = await haracalnde_date(ts_start)
        date_end_pc = await haracalnde_date(ts_end)
        date_range_pc = date_start_pc if date_start_pc == date_end_pc else f'{date_start_pc} to {date_end_pc}'

        # summarize
        summarizer = _get_summarizer()
        try:
            summary = await summarizer.summarize(filtered, ch_cfg, date_range_pc, roster_text)
        except Exception as e:
            logger.error(f'summarization failed for {source_id}: {e!s}')
            return

        # character extraction for the character log channel
        if cfg.character_log_channel_id is not None and channel_id == cfg.character_log_channel_id:
            try:
                extracted = await summarizer.extract_characters(filtered, roster_text)
                for entry in extracted:
                    user_id = entry.get('user_id')
                    character_name = entry.get('character_name')
                    message_id = entry.get('message_id')
                    if user_id and character_name and message_id:
                        source_msg = next((m for m in filtered if m.message_id == message_id), filtered[0])
                        await _get_char_repo().upsert(
                            ChatCharacterDocument(
                                user_id=int(user_id),
                                character_name=str(character_name),
                                first_seen_timestamp=source_msg.created_at,
                                first_seen_message_id=source_msg.message_id,
                                source_channel_id=channel_id,
                            )
                        )
            except Exception as e:
                logger.warn(f'character extraction failed for {source_id}: {e!s}')

        # embed and upsert
        embedder = _get_embedder()
        vector = embedder.embed(summary)
        point_id = str(uuid.uuid4())

        authors = list({str(m.author.id) for m in filtered})
        payload = {
            'source_id': source_id,
            'channel_id': channel_id,
            'channel_name': ch_cfg.name,
            'channel_type': ch_cfg.channel_type,
            'content_type': content_type,
            'authors': authors,
            'timestamp_start': ts_start,
            'timestamp_end': ts_end,
            'timestamp_start_pc': date_start_pc,
            'timestamp_end_pc': date_end_pc,
            'message_ids': [m.message_id for m in filtered],
            'text': summary,
        }

        store = _get_vector_store()
        await store.upsert(_DISCORD_COLLECTION, [PointStruct(id=point_id, vector=vector, payload=payload)])

        await upsert_source(
            ChatSourceDocument(
                source_id=source_id,
                source_type='discord_window',
                content_hash='',  # discord windows don't use content hashing
                last_ingested=int(time.time()),
                qdrant_point_ids=[point_id],
                metadata={
                    'channel_id': channel_id,
                    'message_ids': [m.message_id for m in filtered],
                    'timestamp_start': ts_start,
                    'timestamp_end': ts_end,
                },
            )
        )

        logger.debug(f'ingested discord window {source_id} ({len(filtered)} messages, type={content_type})')


def _format_character_roster(user_nations: dict[str, str], characters: list) -> str:
    """assemble the character roster text from static nations + dynamic character records.
    format: 'Username (user ID): CharName (since DATE)'"""
    if not user_nations and not characters:
        return ''

    char_by_user: dict[int, list] = {}
    for c in characters:
        char_by_user.setdefault(c.user_id, []).append(c)

    lines = []
    for user_id_str, nation in sorted(user_nations.items()):
        uid = int(user_id_str)
        chars = char_by_user.get(uid, [])
        char_strs = [f'{c.character_name} (since {c.first_seen_timestamp})' for c in chars]
        char_part = '; '.join(char_strs) if char_strs else '[no character record]'
        lines.append(f'{nation} (user {uid}): {char_part}')

    # include characters with no nation entry
    for uid, chars in char_by_user.items():
        if str(uid) not in user_nations:
            char_strs = [f'{c.character_name} (since {c.first_seen_timestamp})' for c in chars]
            lines.append(f'(user {uid}): {"; ".join(char_strs)}')

    return '\n'.join(lines)
