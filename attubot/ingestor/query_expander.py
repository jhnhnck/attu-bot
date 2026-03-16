"""
AttuBot - Query Expansion Client (Claude Haiku)
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pathlib import Path

from attubot.client.core import config
from attubot.logging import get_logger


logger = get_logger(__name__)

_HAIKU_MODEL = 'claude-haiku-4-5-20251001'
_EXPAND_MAX_TOKENS = 100

_expander: 'QueryExpander | None' = None


def _get_query_expander() -> 'QueryExpander':
    global _expander  # noqa: PLW0603 - lazy singleton initialization requires global
    if _expander is None:
        _expander = QueryExpander()
    return _expander


class QueryExpander:
    """claude haiku client for expanding user queries into wiki search terms"""

    def __init__(self):
        from anthropic import AsyncAnthropic

        logger.info(f'Initializing query expander ({_HAIKU_MODEL})')
        self._client = AsyncAnthropic(api_key=config.chat.anthropic_api_key)
        self._prompt = (Path(config.chat.prompts_dir) / 'query-expansion-prompt.md').read_text()
        logger.info('Query expander ready')

    async def expand(self, query: str) -> str:
        """return a string of search terms extracted from the query; raises on failure"""
        prompt = self._prompt.format(query=query)
        response = await self._client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=_EXPAND_MAX_TOKENS,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return response.content[0].text.strip()
