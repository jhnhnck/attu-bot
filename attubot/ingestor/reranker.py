"""
AttuBot - Cross-Encoder Reranker Wrapper
Author(s): @jhnhnck <john@jhnhnck.com>

This file is licensed under the Apache License, Version 2.0; See LICENSE for full text.
"""

from attubot.logging import get_logger


logger = get_logger(__name__)

_RERANKER_MODEL = 'cross-encoder/ms-marco-MiniLM-L6-v2'

_reranker: 'Reranker | None' = None


def _get_reranker() -> 'Reranker':
    global _reranker  # noqa: PLW0603 - lazy singleton initialization requires global
    if _reranker is None:
        _reranker = Reranker()
    return _reranker


class Reranker:
    """wraps sentence-transformers CrossEncoder for result reranking"""

    def __init__(self):
        from sentence_transformers import CrossEncoder

        logger.info(f'Loading reranker model: {_RERANKER_MODEL}')
        self._model = CrossEncoder(_RERANKER_MODEL)
        logger.info('Reranker model loaded')

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """score and sort candidates by relevance to query (highest score first)

        each candidate dict must have a 'text' field used for scoring.
        returns the same dicts with a 'rerank_score' key added.
        """
        if not candidates:
            return []

        pairs = [(query, c['text']) for c in candidates]
        scores = self._model.predict(pairs)

        scored = [dict(c, rerank_score=float(s)) for c, s in zip(candidates, scores, strict=True)]
        return sorted(scored, key=lambda x: x['rerank_score'], reverse=True)
