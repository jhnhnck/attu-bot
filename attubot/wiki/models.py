"""
AttuBot - Wiki Data Models
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from pydantic import BaseModel, Field, model_validator


class SearchResult(BaseModel):
    """a single result from the wiki REST search api"""

    title: str
    key: str
    excerpt: str | None = None
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


class PageThumbnail(BaseModel):
    """thumbnail image data returned by the pageimages prop"""

    source: str
    width: int
    height: int


class PageSummary(BaseModel):
    """intro extract and optional thumbnail for a single page"""

    title: str
    extract: str = ''
    thumbnail: PageThumbnail | None = None

    @model_validator(mode='before')
    @classmethod
    def _strip_missing(cls, data: dict) -> dict:
        # mediawiki omits the field entirely when there's no image; normalize to None
        if 'thumbnail' not in data:
            data['thumbnail'] = None
        return data
