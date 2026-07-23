# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki | wiki package."""

from discord import Bot

from nova_core.client.core import config
from nova_core.logging import get_logger
from nova_core.wiki.client import WikiClient
from nova_core.wiki.models import SearchResult, SiteInfo


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
