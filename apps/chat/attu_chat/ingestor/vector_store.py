"""
AttuBot - Qdrant Vector Store Wrapper
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.client.core import config
from attubot.logging import get_logger


logger = get_logger(__name__)

_store: 'VectorStore | None' = None


def _get_vector_store() -> 'VectorStore':
    global _store  # noqa: PLW0603 - lazy singleton initialization requires global
    if _store is None:
        _store = VectorStore(config.chat.qdrant_url)
    return _store


class VectorStore:
    """wraps qdrant_client.AsyncQdrantClient for upsert, search, and delete"""

    def __init__(self, url: str):
        from qdrant_client import AsyncQdrantClient

        logger.info(f'connecting to qdrant at {url}')
        self._client = AsyncQdrantClient(url=url)

    async def ensure_collection(self, name: str, vector_size: int) -> None:
        """create the collection if it does not already exist"""
        from qdrant_client.models import Distance, VectorParams

        existing = {c.name for c in (await self._client.get_collections()).collections}
        if name not in existing:
            logger.info(f'creating qdrant collection: {name} (dim={vector_size})')
            await self._client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
            )

    async def upsert(self, collection: str, points: list) -> None:
        """upsert a list of PointStruct into the collection"""
        await self._client.upsert(collection_name=collection, points=points)

    async def search(self, collection: str, query_vector: list[float], top_k: int, query_filter=None) -> list:
        """vector search; returns a list of ScoredPoint"""
        # TODO(phase2): switch to hybrid search (vector + BM25 sparse) - requires collection schema migration
        from qdrant_client.http.exceptions import UnexpectedResponse

        try:
            result = await self._client.query_points(
                collection_name=collection,
                query=query_vector,
                limit=top_k,
                query_filter=query_filter,
                with_payload=True,
            )
            return result.points
        except UnexpectedResponse as e:
            if e.status_code == 404:
                logger.warn(f'collection `{collection}` not found; returning empty results')
                return []
            raise

    async def delete(self, collection: str, point_ids: list[str]) -> None:
        """delete points by ID from the collection"""
        from qdrant_client.models import PointIdsList

        await self._client.delete(
            collection_name=collection,
            points_selector=PointIdsList(points=point_ids),  # pyright: ignore[reportArgumentType]
        )
