# SPDX-License-Identifier: Apache-2.0
"""doom_bot.wiki | wiki package."""

from discord import Bot

from doom_bot.client.core import config
from doom_bot.logging import get_logger
from doom_bot.wiki.client import WikiClient
from doom_bot.wiki.models import SearchResult, SiteInfo


logger = get_logger(__name__)

# module-level singleton - initialized by setup()
_wiki: WikiClient | None = None


def get_wiki() -> WikiClient:
    """get the global WikiClient instance; raises if not yet initialized"""
    global _wiki  # noqa: PLW0603 - lazy singleton initialization requires global
    if _wiki is None:
        _wiki = WikiClient(endpoint=config.wiki.endpoint)
    return _wiki


def setup(bot: Bot):
    logger.info(f'registered: {__name__}')

    # eagerly initialize so any config errors surface at startup
    get_wiki()


__all__ = [
    'SearchResult',
    'SiteInfo',
    'WikiClient',
    'get_wiki',
    'setup',
]
