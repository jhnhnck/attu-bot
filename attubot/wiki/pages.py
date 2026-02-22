"""
AttuBot - Wiki Page Operations
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import httpx

from attubot.logging import get_logger
from attubot.wiki.auth import AuthApi

logger = get_logger(__name__)


class PagesApi:
    """handles reading and writing wiki pages via the action api"""

    def __init__(self, client: httpx.AsyncClient, action_endpoint: str, auth: AuthApi):
        self._client = client
        self._endpoint = action_endpoint
        self._auth = auth

    async def get(self, page_name: str) -> str:
        """fetch the wikitext content of a page"""
        res = await self._client.get(
            self._endpoint,
            params={
                'action': 'parse',
                'page': page_name,
                'prop': 'wikitext',
                'formatversion': 2,
                'format': 'json',
            },
        )
        res.raise_for_status()
        return res.json()['parse']['wikitext']

    async def edit(self, page_name: str, text: str, reason: str) -> None:
        """overwrite a page with new wikitext content"""
        csrf = await self._auth.get_csrf()

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

        res = await self._client.post(self._endpoint, data=data)
        res.raise_for_status()
        logger.debug(res.text)
