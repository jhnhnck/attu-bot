"""
AttuBot - Wiki Data Models
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pydantic import BaseModel, Field

class SearchResult(BaseModel):
    """a single result from the wiki REST search api"""
    title: str
    key: str
    excerpt: str = ''
    matched_title: str | None = None
    description: str | None = None


class SiteInfo(BaseModel):
    """general site info returned by mediawiki action=siteinfo"""
    server: str
    article_path: str = Field(alias='articlepath')
    site_name: str = Field(alias='sitename', default='')
    generator: str = ''

    def page_url(self, key: str) -> str:
        """build a full URL to a page by its key"""
        return f'{self.server}{self.article_path}'.replace('$1', key)

    model_config = {'populate_by_name': True}
