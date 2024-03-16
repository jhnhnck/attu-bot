"""
AttuBot - Wiki Interactions
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import requests

from attubot.logging import get_logger
logger = get_logger(__name__)

class AttuWiki:
    api_endpoint = 'https://wiki.attuproject.org/api.php'
    session = requests.Session()
    token = ''

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

    def get_page_contents(self, page_name):
        res = self.session.get(self.api_endpoint, params={ 'action': 'parse', 'page': page_name, 'prop': 'wikitext', 'formatversion': 2 , 'format': 'json' })

        return res.json()['parse']['wikitext']

    def edit(self, page_name, text, reason):
        res = self.session.get(self.api_endpoint, params={ 'action': 'query', 'meta': 'tokens', 'format': 'json' })
        csrf = res.json()['query']['tokens']['csrftoken']

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
        res = self.session.get(self.api_endpoint, params={ 'action': 'query', 'meta': 'tokens', 'format': 'json' })
        csrf = res.json()['query']['tokens']['csrftoken']

        data = {
            'action': 'block',
            'user': user,
            'expiry': 'never',
            'reason': reason,
            'nocreate': True,
            'noemail': True,
            'allowusertalk': False,
            'partial': False,
            'token': csrf,
            'format': 'json',
        }

        res = self.session.post(self.api_endpoint, data=data)
        logger.debug(res.text)

        return res.json()
