# SPDX-License-Identifier: Apache-2.0
"""doom_bot.wiki.search | wiki search."""

import httpx

from doom_bot.logging import get_logger
from doom_bot.wiki.models import SearchResult, SiteInfo


logger = get_logger(__name__)


class SearchApi:
    """handles wiki search and general site info via the REST and action apis"""

    def __init__(self, client: httpx.AsyncClient, action_endpoint: str, rest_endpoint: str):
        self._client = client
        self._action = action_endpoint
        self._rest = rest_endpoint

    async def search(self, query: str, limit: int) -> list[SearchResult]:
        """search for wiki pages matching the query (full-text, title + body)"""
        res = await self._client.get(
            f'{self._rest}/search/page',
            params={'q': query, 'limit': limit},
        )
        res.raise_for_status()
        logger.debug(f'req: "{res.request.url}"')
        logger.debug(res.text)

        # the api doesn't always respect limit so truncate manually
        raw = res.json().get('pages', [])[:limit]
        return [SearchResult.model_validate(page) for page in raw]

    async def search_title(self, query: str, limit: int) -> list[SearchResult]:
        """search for wiki pages by title only"""
        res = await self._client.get(
            f'{self._rest}/search/title',
            params={'q': query, 'limit': limit},
        )
        res.raise_for_status()
        logger.debug(f'req: "{res.request.url}"')
        logger.debug(res.text)

        raw = res.json().get('pages', [])[:limit]
        return [SearchResult.model_validate(page) for page in raw]

    async def site_info(self) -> SiteInfo:
        """fetch general site information"""
        data = {
            'action': 'query',
            'format': 'json',
            'meta': 'siteinfo',
            'formatversion': '2',
            'siprop': 'general',
        }

        res = await self._client.post(self._action, data=data)
        res.raise_for_status()
        logger.debug(res.text)

        return SiteInfo.model_validate(res.json()['query']['general'])
