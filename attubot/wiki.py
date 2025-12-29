"""
AttuBot - Wiki Interactions
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import asyncio
from platform import python_version

import httpx

from attubot import __email__, __title__, __version__
from attubot.config import NovaConfig
from attubot.logging import get_logger
from attubot.util import create_task

logger = get_logger(__name__)

class AttuWiki:
    client: httpx.AsyncClient
    token: str = ''
    max_retries: int = 3

    def __init__(self):
        self.client = httpx.AsyncClient(
            base_url=NovaConfig.wiki.endpoint,
            headers={'User-Agent': f'{__title__}/{__version__} ({__email__}) httpx/{httpx.__version__} Python/{python_version()}'},
        )

        self.action_endpoint = '/api.php'
        self.rest_endpoint = '/rest.php/v1'

    def __del__(self):
        logger.debug(f'Closing out httpx session: {self.client}')

        create_task(self.client.aclose(), 'HttpxClientClose')

    # TODO: convert these into an AuthProvider
    async def _get_csrf(self) -> str:
        res = await self.client.get(self.action_endpoint, params={'action': 'query', 'meta': 'tokens', 'format': 'json'})
        return res.json()['query']['tokens']['csrftoken']

    async def authenticate(self, user: str, key: str):
        res = await self.client.get(self.action_endpoint, params={'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'})
        self.token = res.json()['query']['tokens']['logintoken']

        data = {
            'action': 'login',
            'lgname': user,
            'lgpassword': key,
            'lgtoken': self.token,
            'format': 'json',
        }

        res = await self.client.post(self.action_endpoint, data=data)
        logger.debug(res.text)

    async def get_page_contents(self, page_name: str):
        res = await self.client.get(self.action_endpoint, params={'action': 'parse', 'page': page_name, 'prop': 'wikitext', 'formatversion': 2, 'format': 'json'})
        return res.json()['parse']['wikitext']

    async def edit(self, page_name: str, text: str, reason: str):
        csrf = await self._get_csrf()

        data = {
            'action': 'edit',
            'title': page_name,
            'token': csrf,
            'format': 'json',
            'text': text,
            'bot': True,
            'minor': True,
            'summary': reason,
        }

        res = await self.client.post(self.action_endpoint, data=data)
        logger.debug(res.text)

    async def block(self, user: str, reason: str):
        csrf = await self._get_csrf()

        data = {
            'action': 'block',
            'format': 'json',
            'user': user,
            'expiry': 'never',
            'reason': reason,
            'nocreate': True,
            'autoblock': True,
            'noemail': True,
            'reblock': True,
            'token': csrf,
        }

        # retry a few times in case of connection aborted
        for attempt in range(self.max_retries):
            try:
                res = await self.client.post(self.action_endpoint, data=data)
                logger.debug(res.text)

                return res.json()

            except Exception as error:
                logger.error(f'block(): Attempt {attempt + 1} failed with error: {error}')
                await asyncio.sleep(3)

        return False

    async def search(self, query: str, limit: int):
        res = await self.client.get(f'{self.rest_endpoint}/search/page', params={'q': query, 'limit': limit})
        logger.debug(f'Req: "{res.request.url}"')
        logger.debug(res.text)

        return res.json()['pages'][:limit]  # currently doesn't respect limit so manually truncate here

    async def site_info(self):
        data = {'action': 'query', 'format': 'json', 'meta': 'siteinfo', 'formatversion': '2', 'siprop': 'general'}

        res = await self.client.post(self.action_endpoint, data=data)
        logger.debug(res.text)

        return res.json()['query']['general']
