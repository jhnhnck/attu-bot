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

from attubot.core import config
from attubot.logging import get_logger
from attubot.util import is_authorized_guild, is_bot_owner


logger = get_logger(__name__)

# per-user cooldown tracking (monotonic time, not wall clock)
_ask_last_used: dict[int, float] = {}

# cached system prompt - loaded lazily on first /ask call
_system_prompt: str | None = None


def _get_system_prompt() -> str:
    global _system_prompt  # noqa: PLW0603 - lazy singleton initialization requires global
    if _system_prompt is None:
        path = Path(config.chat.prompts_dir) / 'chat-system-prompt.md'
        _system_prompt = path.read_text()
        logger.debug(f'Loaded system prompt from {path}')
    return _system_prompt


def _build_context_block(results: list[dict]) -> str:
    """format reranked results into a context block for the LLM prompt"""
    lines: list[str] = []
    for r in results:
        payload = r.get('payload', {})
        title = payload.get('page_title', 'Unknown')
        section = payload.get('section', '')
        text = payload.get('text', '')
        header = f'[WIKI - authoritative] {title}'
        if section and section != '(intro)':
            header += f' > {section}'
        lines.append(f'{header}\n{text}')
    return '\n\n---\n\n'.join(lines)


@discord.slash_command(name='ask', description='Ask the lore assistant a question about the Attu world')
@discord.commands.check(is_bot_owner)  # TODO(release): remove - testing phase only
@discord.commands.check(is_authorized_guild)
@option('query', description='Your question about the Attu world', required=True)
async def command_ask(ctx: ApplicationContext, query: str):
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
        from attubot.calendar import haracalnde_date
        from attubot.ingestor.embedder import _get_embedder
        from attubot.ingestor.llm import _get_llm
        from attubot.ingestor.reranker import _get_reranker
        from attubot.ingestor.vector_store import _get_vector_store

        # 1. embed the query
        embedder = _get_embedder()
        query_vector = embedder.embed(query)

        # 2. search qdrant wiki collection
        store = _get_vector_store()
        top_k = config.chat_runtime.retrieval_top_k_wiki
        raw_results = await store.search('wiki', query_vector, top_k=top_k)

        if not raw_results:
            await ctx.respond("I don't have reliable information about that.")
            return

        # 3. rerank
        # TODO(phase2): cap reranked results to top 8 after multi-source search (wiki+discord+docs+images)
        reranker = _get_reranker()
        candidates = [{'text': r.payload.get('text', ''), 'payload': r.payload} for r in raw_results]
        reranked = reranker.rerank(query, candidates)

        # 4. assemble context block
        context = _build_context_block(reranked)

        # 5. inject current date into system prompt (character roster empty in phase 1)
        guild_id = ctx.guild_id
        current_date = await haracalnde_date(int(time.time()), guild_id)
        system = _get_system_prompt().format(
            current_date_pc=current_date,
            character_roster='',
        )

        # 6. stream LLM response
        llm = _get_llm()
        buffer = ''
        last_edit = time.monotonic()
        edit_interval = 1.5  # seconds between message edits while streaming

        async for token in llm.complete(system, context, query):
            buffer += token
            now = time.monotonic()
            if now - last_edit >= edit_interval:
                await ctx.edit(content=buffer + '\u25aa')  # trailing indicator while streaming
                last_edit = now

        # 7. final response with source citations
        sources: list[str] = []
        seen_sources: set[str] = set()
        for r in reranked:
            payload = r.get('payload', {})
            title = payload.get('page_title', '')
            if title and title not in seen_sources:
                seen_sources.add(title)
                sources.append(f'[wiki: {title}]')

        citation_line = '\n\n-# ' + ' '.join(sources) if sources else ''
        await ctx.edit(content=buffer + citation_line)

    except Exception as e:
        logger.error(f'/ask command failed: {e!s}')
        await ctx.edit(content='Something went wrong processing your question. Please try again.')


def setup(bot: Bot):
    bot.add_application_command(cast(ApplicationCommand, command_ask))
