"""
AttuBot - Wiki Ingestion Pipeline
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

import hashlib
import re
import time
import uuid

import mwparserfromhell

from attubot.client.core import config
from attubot.database.models import ChatSourceDocument
from attubot.ingestor.embedder import _get_embedder
from attubot.ingestor.registry import get_source, upsert_source
from attubot.ingestor.vector_store import _get_vector_store
from attubot.logging import get_logger
from attubot.wiki import get_wiki


logger = get_logger(__name__)

_WIKI_COLLECTION = 'wiki'


def _slugify(text: str) -> str:
    """convert a title/section string to a safe source_id component"""
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')


def _section_source_id(page_title: str, section_title: str) -> str:
    return f'wiki_{_slugify(page_title)}_{_slugify(section_title or "intro")}'


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class WikiPipeline:
    """fetches wiki pages, splits into sections, embeds, and upserts into qdrant"""

    async def run_initial_ingest(self) -> None:
        """ingest all pages in the configured namespaces - use for bootstrapping"""
        wiki = get_wiki()
        for ns in config.chat_runtime.wiki_namespaces:
            logger.info(f'initial wiki ingest: namespace {ns}')
            titles = await wiki.pages.get_all_pages(namespace=ns)
            logger.info(f'found [{len(titles)}] pages in namespace {ns}')
            for title in titles:
                await self._ingest_page(title)

    async def run_recent_changes(self) -> None:
        """ingest pages changed in the last ~65 minutes; falls back to initial ingest if collection is empty"""
        store = _get_vector_store()
        embedder = _get_embedder()

        # ensure the collection exists
        await store.ensure_collection(_WIKI_COLLECTION, embedder.dim)

        # check if collection is empty - if so, do a full ingest first
        try:
            results = await store.search(_WIKI_COLLECTION, [0.0] * embedder.dim, top_k=1)
            collection_empty = len(results) == 0
        except Exception:
            collection_empty = True

        if collection_empty:
            logger.info('wiki collection is empty - running initial ingest')
            await self.run_initial_ingest()
            return

        wiki = get_wiki()
        for ns in config.chat_runtime.wiki_namespaces:
            titles = await wiki.pages.get_recent_changes(minutes=65, namespace=ns)
            if titles:
                logger.info(f'wiki recent changes: [{len(titles)}] page(s) in namespace {ns}')
            for title in titles:
                await self._ingest_page(title)

    async def _ingest_page(self, title: str) -> None:
        """fetch, parse, split, and embed a single wiki page"""
        logger.info(f'ingesting "{title}"')
        wiki = get_wiki()

        try:
            wikitext, revid, rev_timestamp, categories = await wiki.pages.get_with_revision(title)
        except Exception as e:
            logger.warn(f'failed to fetch wiki page "{title}": {e!s}')
            return

        sections = _parse_sections(wikitext)
        if not sections:
            logger.debug(f'no sections found in "{title}"; skipping')
            return

        store = _get_vector_store()
        embedder = _get_embedder()

        for section_title, section_text in sections:
            if not section_text.strip():
                continue

            source_id = _section_source_id(title, section_title)
            content_hash = _content_hash(f'{title}:{section_text}')

            # skip if content unchanged
            existing = await get_source(source_id)
            if existing and existing.content_hash == content_hash and not existing.flagged_incorrect:
                logger.trace(f'Skipping unchanged section: {source_id}')
                continue

            # embed title + section heading + body + categories for better term overlap
            embed_prefix = f'{title} - {section_title}' if section_title else title
            embed_text = f'{embed_prefix}: {section_text}'
            if categories:
                embed_text += f'\nCategories: {", ".join(categories)}'
            vector = embedder.embed(embed_text)

            # upsert into qdrant
            point_id = str(uuid.uuid4())
            from qdrant_client.models import PointStruct

            payload = {
                'source_id': source_id,
                'page_title': title,
                'section': section_title or '(intro)',
                'revision_id': revid,
                'timestamp': rev_timestamp,
                'source_of_truth': True,
                'text': section_text,
                'categories': categories,
            }
            await store.upsert(_WIKI_COLLECTION, [PointStruct(id=point_id, vector=vector, payload=payload)])

            # update chat_sources
            await upsert_source(
                ChatSourceDocument(
                    source_id=source_id,
                    source_type='wiki_section',
                    content_hash=content_hash,
                    last_ingested=int(time.time()),
                    qdrant_point_ids=[point_id],
                    metadata={'page_title': title, 'section': section_title or '(intro)', 'categories': categories},
                )
            )

            logger.debug(f'ingested wiki section: {source_id}')


def _parse_sections(wikitext: str) -> list[tuple[str, str]]:
    """parse wikitext into (section_title, plain_text) pairs

    returns one entry per == heading == section, plus the intro before the first heading.
    """
    parsed = mwparserfromhell.parse(wikitext)
    sections: list[tuple[str, str]] = []

    for section in parsed.get_sections(include_lead=True, flat=True):
        headings = section.filter_headings()
        title = headings[0].title.strip() if headings else ''
        text = section.strip_code().strip()
        if text:
            sections.append((title, text))

    return sections
