"""
AttuBot - Claude Haiku Summarization Client
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import json
from pathlib import Path

from attu_models import ChatChannelConfig, MessageDocument
from doom_bot.client.core import config
from doom_bot.logging import get_logger


logger = get_logger(__name__)

_HAIKU_MODEL = 'claude-haiku-4-5-20251001'
_SUMMARIZE_MAX_TOKENS = 512
_EXTRACT_MAX_TOKENS = 256

_summarizer: 'Summarizer | None' = None


def _get_summarizer() -> 'Summarizer':
    global _summarizer  # noqa: PLW0603 - lazy singleton initialization requires global
    if _summarizer is None:
        _summarizer = Summarizer()
    return _summarizer


def _format_messages(messages: list[MessageDocument]) -> str:
    """format a list of messages as 'AuthorName (id): text' lines"""
    lines = []
    for m in messages:
        text = m.content.text.strip()
        if text:
            lines.append(f'{m.author.name} ({m.author.id}): {text}')
    return '\n'.join(lines)


class Summarizer:
    """claude haiku client for discord window summarization and character extraction"""

    def __init__(self):
        from anthropic import AsyncAnthropic

        logger.info(f'initializing summarizer ({_HAIKU_MODEL})')
        self._client = AsyncAnthropic(api_key=config.chat.anthropic_api_key)

        prompts_dir = Path(config.chat.prompts_dir)
        self._summarize_prompt = (prompts_dir / 'discord-summarization-prompt.md').read_text()
        self._extract_prompt = (prompts_dir / 'character-extraction-prompt.md').read_text()
        logger.info('summarizer ready')

    async def summarize(
        self,
        messages: list[MessageDocument],
        channel_cfg: ChatChannelConfig,
        date_range_pc: str,
        character_roster: str,
    ) -> str:
        """summarize a discord window; returns a dense semantic summary string"""
        authors = ', '.join(sorted({m.author.name for m in messages}))
        formatted = _format_messages(messages)
        prompt = self._summarize_prompt.format(
            channel=channel_cfg.name,
            channel_type=channel_cfg.channel_type,
            authors=authors,
            date_range_pc=date_range_pc,
            character_roster=character_roster or '(none yet)',
            messages=formatted,
        )
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=_SUMMARIZE_MAX_TOKENS,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return response.content[0].text.strip()

    async def extract_characters(
        self,
        messages: list[MessageDocument],
        roster_text: str,
    ) -> list[dict]:
        """extract character introductions from a window; returns list of dicts or [] on failure"""
        formatted = _format_messages(messages)
        prompt = self._extract_prompt.format(
            character_roster=roster_text or '(none yet)',
            messages=formatted,
        )
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=_EXTRACT_MAX_TOKENS,
            messages=[{'role': 'user', 'content': prompt}],
        )
        raw = response.content[0].text.strip()
        try:
            result = json.loads(raw)
            if isinstance(result, list):
                return result
            logger.warn(f'character extraction returned non-list json: {raw[:200]}')
            return []
        except json.JSONDecodeError:
            logger.warn(f'character extraction returned invalid json: {raw[:200]}')
            return []
