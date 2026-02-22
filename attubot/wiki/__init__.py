"""
AttuBot - Wiki Package
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from discord import Bot

from attubot.logging import get_logger
from attubot.wiki.client import WikiClient
from attubot.wiki.models import SearchResult, SiteInfo

logger = get_logger(__name__)

# module-level singleton - initialized by setup()
_wiki: WikiClient | None = None


def get_wiki() -> WikiClient:
    """get the global WikiClient instance; raises if not yet initialized"""
    global _wiki  # noqa: PLW0603
    if _wiki is None:
        from attubot import config
        _wiki = WikiClient(endpoint=config.wiki.endpoint)
    return _wiki


def setup(bot: Bot):
    logger.info(f'Registered: {__name__}')

    # eagerly initialize so any config errors surface at startup
    get_wiki()


__all__ = [
    'SearchResult',
    'SiteInfo',
    'WikiClient',
    'get_wiki',
    'setup',
]
