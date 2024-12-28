"""
AttuBot - Wiki Interactions
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import time
from platform import python_version

import requests

from attubot import __email__, __title__, __version__
from attubot.config import Config
from attubot.logging import get_logger

logger = get_logger(__name__)

class AttuWiki:
    session = None
    token = ''
    max_retries = 3

    def __init__(self):
        self.session = requests.Session()
        self.session.headers = {'User-Agent': f'{__title__}/{__version__} ({__email__}) Requests/{requests.__version__} Python/{python_version()}'}

        self.action_endpoint = f'{Config.wiki_endpoint}/api.php'
        self.rest_endpoint = f'{Config.wiki_endpoint}/rest.php/v1'

    def _get_csrf(self):
        res = self.session.get(self.action_endpoint, params={'action': 'query', 'meta': 'tokens', 'format': 'json'})
        return res.json()['query']['tokens']['csrftoken']

    # def _debug(self, response):
    #     from requests_toolbelt.utils import dump
    #     data = dump.dump_all(response)
    #     logger.debug(data.decode('utf-8'))

    # TODO: Make use config instead of passed args
    def authenticate(self, user, key):
        res = self.session.get(self.action_endpoint, params={'action': 'query', 'meta': 'tokens', 'type': 'login', 'format': 'json'})
        self.token = res.json()['query']['tokens']['logintoken']

        data = {
            'action': 'login',
            'lgname': user,
            'lgpassword': key,
            'lgtoken': self.token,
            'format': 'json',
        }

        res = self.session.post(self.action_endpoint, data=data)
        logger.debug(res.text)

    def get_page_contents(self, page_name):
        res = self.session.get(self.action_endpoint, params={'action': 'parse', 'page': page_name, 'prop': 'wikitext', 'formatversion': 2, 'format': 'json'})
        return res.json()['parse']['wikitext']

    def edit(self, page_name, text, reason):
        csrf = self._get_csrf()

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

        res = self.session.post(self.action_endpoint, data=data)
        logger.debug(res.text)

    def block(self, user, reason):
        csrf = self._get_csrf()

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
                res = self.session.post(self.action_endpoint, data=data)
                logger.debug(res.text)

                return res.json()

            except Exception as error:
                logger.error(f'block(): Attempt {attempt + 1} failed with error: {error}')
                time.sleep(3)

        return False

    def search(self, query, limit):
        res = self.session.get(f'{self.rest_endpoint}/search/page', params={'q': query, 'limit': limit})
        logger.debug(f'Req: "{res.request.url}"')
        logger.debug(res.text)

        return res.json()['pages'][:limit]  # currently doesn't respect limit so manually truncate here

    def site_info(self):
        data = {'action': 'query', 'format': 'json', 'meta': 'siteinfo', 'formatversion': '2', 'siprop': 'general'}

        res = self.session.post(self.action_endpoint, data=data)
        logger.debug(res.text)

        return res.json()['query']['general']
