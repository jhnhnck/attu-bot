"""
AttuBot - Sentence Embedding Wrapper
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.client.core import config
from attubot.logging import get_logger


logger = get_logger(__name__)

_embedder: 'Embedder | None' = None


def _get_embedder() -> 'Embedder':
    global _embedder  # noqa: PLW0603 - lazy singleton initialization requires global
    if _embedder is None:
        _embedder = Embedder(config.chat.embedding_model)
    return _embedder


class Embedder:
    """wraps sentence-transformers SentenceTransformer for text embedding"""

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        logger.info(f'Loading embedding model: {model_name}')
        self._model = SentenceTransformer(model_name)
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info(f'Embedding model loaded (dim={self._dim})')

    @property
    def dim(self) -> int:
        if self._dim is None:
            raise RuntimeError('embedding model did not report a dimension')
        return self._dim

    def embed(self, text: str) -> list[float]:
        """embed a single text string; returns a float vector"""
        return self._model.encode(text, convert_to_numpy=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """embed a list of texts; returns a list of float vectors"""
        return self._model.encode(texts, convert_to_numpy=True).tolist()
