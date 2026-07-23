# SPDX-License-Identifier: Apache-2.0
"""nova_core.wiki.pages | wiki page operations."""

import httpx
import structlog

from nova_core.wiki.auth import AuthApi
from nova_core.wiki.models import PageSummary


logger = structlog.stdlib.get_logger(__name__)


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

    async def get_summary(self, page_name: str) -> PageSummary | None:
        """fetch the intro extract and thumbnail for a specific page; returns None if the page doesn't exist"""
        res = await self._client.get(
            self._endpoint,
            params={
                'action': 'query',
                'format': 'json',
                'titles': page_name,
                'prop': 'extracts|pageimages',
                'exintro': 1,
                'explaintext': 1,
                'pithumbsize': 500,
                'formatversion': 2,
            },
        )
        res.raise_for_status()
        pages = res.json().get('query', {}).get('pages', [])
        if not pages or pages[0].get('pageid', -1) == -1:
            return None
        return PageSummary.model_validate(pages[0])

    async def get_random_summary(self, namespace: int = 0) -> PageSummary:
        """fetch the intro extract and thumbnail for a random page in the given namespace"""
        res = await self._client.get(
            self._endpoint,
            params={
                'action': 'query',
                'format': 'json',
                'generator': 'random',
                'grnnamespace': namespace,
                'prop': 'extracts|pageimages',
                'exintro': 1,
                'explaintext': 1,
                'pithumbsize': 500,
                'formatversion': 2,
            },
        )
        res.raise_for_status()
        pages = res.json()['query']['pages']
        return PageSummary.model_validate(pages[0])

    async def get_with_revision(self, page_name: str) -> tuple[str, int, str, list[str]]:
        """fetch wikitext along with the current revid, ISO timestamp, and page categories"""
        res = await self._client.get(
            self._endpoint,
            params={
                'action': 'query',
                'titles': page_name,
                'prop': 'revisions|categories',
                'rvprop': 'ids|timestamp|content',
                'rvslots': 'main',
                'cllimit': 'max',
                'formatversion': 2,
                'format': 'json',
            },
        )
        res.raise_for_status()
        page = res.json()['query']['pages'][0]
        rev = page['revisions'][0]
        cats = [c['title'].removeprefix('Category:') for c in page.get('categories', [])]
        return rev['slots']['main']['content'], rev['revid'], rev['timestamp'], cats

    async def get_all_pages(self, namespace: str = '0') -> list[str]:
        """fetch all page titles in the given namespace via allpages with pagination"""
        titles: list[str] = []
        apcontinue: str | None = None

        while True:
            params: dict = {
                'action': 'query',
                'list': 'allpages',
                'apnamespace': namespace,
                'aplimit': 'max',
                'format': 'json',
                'formatversion': 2,
            }
            if apcontinue is not None:
                params['apcontinue'] = apcontinue

            res = await self._client.get(self._endpoint, params=params)
            res.raise_for_status()
            data = res.json()

            for page in data.get('query', {}).get('allpages', []):
                titles.append(page['title'])

            cont = data.get('continue', {})
            apcontinue = cont.get('apcontinue')
            if apcontinue is None:
                break

        return titles

    async def get_recent_changes(self, minutes: int = 65, namespace: str = '0') -> list[str]:
        """fetch titles of pages changed in the last N minutes in the given namespace"""
        import datetime

        since = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=minutes)).strftime('%Y-%m-%dT%H:%M:%SZ')

        res = await self._client.get(
            self._endpoint,
            params={
                'action': 'query',
                'list': 'recentchanges',
                'rcnamespace': namespace,
                'rcstart': since,
                'rcdir': 'newer',
                'rctype': 'edit|new',
                'rcprop': 'title',
                'rclimit': 'max',
                'format': 'json',
                'formatversion': 2,
            },
        )
        res.raise_for_status()
        changes = res.json().get('query', {}).get('recentchanges', [])
        # deduplicate - a page may appear multiple times if edited repeatedly
        seen: set[str] = set()
        titles: list[str] = []
        for change in changes:
            title = change['title']
            if title not in seen:
                seen.add(title)
                titles.append(title)
        return titles
