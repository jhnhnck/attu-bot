"""
AttuBot - Wiki Interactions
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import requests

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
        print(res.text)
