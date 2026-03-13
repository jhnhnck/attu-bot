"""
AttuBot - Chat/RAG Slash Commands (/ask)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time
from pathlib import Path
from typing import cast

import discord
from discord import ApplicationCommand, ApplicationContext, Bot
from discord.commands import option
from discord.ext import commands

from attubot.client.calendar import haracalnde_date
from attubot.client.core import config
from attubot.client.util import is_authorized_guild, is_bot_owner
from attubot.database.models import ChatCharacterDocument
from attubot.ingestor.embedder import _get_embedder
from attubot.ingestor.llm import _get_llm
from attubot.ingestor.reranker import _get_reranker
from attubot.ingestor.vector_store import _get_vector_store
from attubot.logging import get_logger


logger = get_logger(__name__)

# per-user cooldown tracking (monotonic time, not wall clock)
_ask_last_used: dict[int, float] = {}

# cached system prompt - loaded lazily on first /ask call
_system_prompt: str | None = None

_char_repo = None


def _get_char_repo():
    global _char_repo  # noqa: PLW0603 - lazy singleton initialization requires global
    if _char_repo is None:
        from attubot import db
        from attubot.database.repositories import ChatCharacterRepository
        _char_repo = ChatCharacterRepository(db.get_db())
    return _char_repo


def _get_system_prompt() -> str:
    global _system_prompt  # noqa: PLW0603 - lazy singleton initialization requires global
    if _system_prompt is None:
        path = Path(config.chat.prompts_dir) / 'chat-system-prompt.md'
        _system_prompt = path.read_text()
        logger.debug(f'Loaded system prompt from {path}')
    return _system_prompt


def _format_character_roster(user_nations: dict[str, str], characters: list[ChatCharacterDocument]) -> str:
    """assemble the character roster text from static nations + dynamic character records"""
    if not user_nations and not characters:
        return ''

    char_by_user: dict[int, list[ChatCharacterDocument]] = {}
    for c in characters:
        char_by_user.setdefault(c.user_id, []).append(c)

    lines = []
    for user_id_str, nation in sorted(user_nations.items()):
        uid = int(user_id_str)
        chars = char_by_user.get(uid, [])
        char_strs = [c.character_name for c in chars]
        char_part = '; '.join(char_strs) if char_strs else '[no character record]'
        lines.append(f'{nation} (user {uid}): {char_part}')

    # include characters with no nation entry
    for uid, chars in char_by_user.items():
        if str(uid) not in user_nations:
            char_strs = [c.character_name for c in chars]
            lines.append(f'(user {uid}): {"; ".join(char_strs)}')

    return '\n'.join(lines)


def _build_context_block(results: list[dict]) -> str:
    """format reranked results into a context block for the LLM prompt"""
    lines: list[str] = []
    for r in results:
        payload = r.get('payload', {})
        text = payload.get('text', '')

        if payload.get('source_of_truth'):
            # wiki source
            title = payload.get('page_title', 'Unknown')
            section = payload.get('section', '')
            header = f'[WIKI - authoritative] {title}'
            if section and section != '(intro)':
                header += f' > {section}'
        else:
            # discord source
            channel_name = payload.get('channel_name', 'unknown')
            date_pc = payload.get('timestamp_start_pc', '')
            header = f'[DISCORD - #{channel_name}, {date_pc}]'

        lines.append(f'{header}\n{text}')
    return '\n\n---\n\n'.join(lines)


@discord.slash_command(name='ask', description='Ask the lore assistant a question about the Attu world')
@commands.check(is_bot_owner)  # TODO(release): remove - testing phase only
@commands.check(is_authorized_guild)
@option('query', description='Your question about the Attu world', required=True)
async def command_ask(ctx: ApplicationContext, query: str):  # noqa: PLR0915
    # cooldown check
    cooldown = config.chat.ask_cooldown_seconds
    if cooldown > 0:
        now = time.monotonic()
        last = _ask_last_used.get(ctx.user.id, 0.0)
        if now - last < cooldown:
            remaining = int(cooldown - (now - last))
            await ctx.respond(f'please wait {remaining}s before asking again', ephemeral=True)
            return
        _ask_last_used[ctx.user.id] = now

    await ctx.defer()

    try:
        # 1. embed the query
        embedder = _get_embedder()
        query_vector = embedder.embed(query)

        # 2. search qdrant wiki + discord collections
        store = _get_vector_store()
        wiki_results = await store.search('wiki', query_vector, top_k=config.chat_runtime.retrieval_top_k_wiki)
        discord_results = await store.search('discord', query_vector, top_k=config.chat_runtime.retrieval_top_k_discord)
        raw_results = wiki_results + discord_results

        if not raw_results:
            await ctx.respond(f"> {query}\nI don't have reliable information about that.")
            return

        # 3. rerank all candidates together; cap to top 8
        reranker = _get_reranker()
        candidates = [{'text': r.payload.get('text', ''), 'payload': r.payload} for r in raw_results]
        reranked = reranker.rerank(query, candidates)[:8]
        for r in reranked:
            source = 'wiki' if r.get('payload', {}).get('source_of_truth') else 'discord'
            label = r.get('payload', {}).get('page_title') or r.get('payload', {}).get('channel_name', '?')
            score = r.get('rerank_score', 0)
            logger.debug(f'rerank: {score:.3f} [{source}] {label}')

        # 4. assemble context block
        context = _build_context_block(reranked)

        # 5. inject current date + character roster into system prompt
        guild_id = ctx.guild_id
        current_date = await haracalnde_date(int(time.time()), guild_id)
        characters = await _get_char_repo().get_all()
        roster_text = _format_character_roster(config.chat_runtime.user_nations, characters)
        system = _get_system_prompt().format(
            current_date_pc=current_date,
            character_roster=roster_text,
        )

        # 6. stream LLM response
        llm = _get_llm()
        logger.debug(f'llm system prompt:\n{system}')
        logger.debug(f'llm user message:\n{context}\n\n<query>{query}</query>')
        prefix = f'> {query}\n'
        buffer = ''
        last_edit = time.monotonic()
        edit_interval = 1.5  # seconds between message edits while streaming

        async for token in llm.complete(system, context, query):
            buffer += token
            now = time.monotonic()
            if now - last_edit >= edit_interval:
                await ctx.edit(content=prefix + buffer + '\u25aa')  # trailing indicator while streaming
                last_edit = now

        # 7. final response with source citations (only sources with positive rerank score)
        sources: list[str] = []
        seen_sources: set[str] = set()
        relevant = [r for r in reranked if r.get('rerank_score', 0) > 0] or reranked[:1]
        for r in relevant:
            payload = r.get('payload', {})
            if payload.get('source_of_truth'):
                title = payload.get('page_title', '')
                if title and title not in seen_sources:
                    seen_sources.add(title)
                    sources.append(f'[wiki: {title}]')
            else:
                channel = payload.get('channel_name', '')
                date_pc = payload.get('timestamp_start_pc', '')
                label = f'#{channel}' + (f', {date_pc}' if date_pc else '')
                if label not in seen_sources:
                    seen_sources.add(label)
                    sources.append(f'[{label}]')

        citation_line = '\n-# ' + ' '.join(sources) if sources else ''
        await ctx.edit(content=prefix + buffer.strip() + citation_line)

    except Exception as e:
        logger.error(f'/ask command failed: {e!s}')
        await logger.send_to_webhook(e)
        await ctx.edit(content='Something went wrong processing your question. Please try again.')


def setup(bot: Bot):
    bot.add_application_command(cast(ApplicationCommand, command_ask))
