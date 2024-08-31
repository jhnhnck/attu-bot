"""
AttuBot - Wiki Interactions
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import requests
# from requests_toolbelt.utils import dump

from attubot.logging import get_logger
logger = get_logger(__name__)

class AttuWiki:
    api_endpoint = 'https://attuproject.org/api.php'
    session = requests.Session()
    token = ''

    def _get_csrf(self):
        res = self.session.get(self.api_endpoint, params={ 'action': 'query', 'meta': 'tokens', 'format': 'json' })
        return res.json()['query']['tokens']['csrftoken']

    # def _debug(self, response):
    #     data = dump.dump_all(response)
    #     logger.debug(data.decode('utf-8'))

    def authenticate(self, user, key):
        res = self.session.get(self.api_endpoint, params={ 'action':"query", 'meta': 'tokens', 'type': 'login', 'format': 'json' })
        self.token = res.json()['query']['tokens']['logintoken']

        data = {
            'action': 'login',
            'lgname': user,
            'lgpassword': key,
            'lgtoken': self.token,
            'format': 'json'
        }

        res = self.session.post(self.api_endpoint, data=data)
        logger.debug(res.text)

    def get_page_contents(self, page_name):
        res = self.session.get(self.api_endpoint, params={ 'action': 'parse', 'page': page_name, 'prop': 'wikitext', 'formatversion': 2 , 'format': 'json' })
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

        res = self.session.post(self.api_endpoint, data=data)
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

        res = self.session.post(self.api_endpoint, data=data)
        logger.debug(res.text)

        return res.json()
