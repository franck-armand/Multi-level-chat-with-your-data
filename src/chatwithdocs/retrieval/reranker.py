from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class RerankedResult:
    """Result after reranking."""

    id: str
    content: str
    score: float  # Reranker score
    original_score: float  # Original retrieval score
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CrossEncoderReranker:
    """Reranker using cross-encoder model.

    Cross-encoders provide more accurate relevance scoring by
    processing query and document together, but are slower than
    bi-encoders (embedding models).
    """

    DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or self.DEFAULT_MODEL
        self._model = None

    def _load_model(self):
        """Lazy load the cross-encoder model."""
        if self._model is None:
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"Loading cross-encoder model: {self.model_name}")
                self._model = CrossEncoder(self.model_name)
                logger.info("Cross-encoder model loaded")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: uv pip install sentence-transformers"
                )
            except Exception as e:
                logger.error(f"Failed to load cross-encoder: {e}")
                raise

    def rerank(
        self,
        query: str,
        results: List[RerankedResult],
        top_k: int | None = None,
    ) -> List[RerankedResult]:
        """Rerank results using cross-encoder.

        Args:
            query: Search query
            results: List of results to rerank
            top_k: Number of top results to return (default: settings.rerank_top_k)

        Returns:
            Reranked list of results
        """
        if not results:
            return []

        if not settings.rerank_results:
            # Reranking disabled, return original order
            return results[: (top_k or settings.rerank_top_k)]

        self._load_model()

        # Prepare pairs for cross-encoder
        pairs = [(query, r.content) for r in results]

        try:
            # Get scores from cross-encoder
            scores = self._model.predict(pairs)

            # Update results with new scores
            reranked = []
            for result, score in zip(results, scores):
                reranked.append(
                    RerankedResult(
                        id=result.id,
                        content=result.content,
                        score=float(score),
                        original_score=result.score,
                        metadata=result.metadata,
                    )
                )

            # Sort by new score (descending)
            reranked.sort(key=lambda x: x.score, reverse=True)

            # Return top-k
            k = top_k or settings.rerank_top_k
            return reranked[:k]

        except Exception as e:
            logger.error(f"Reranking failed: {e}")
            # Fallback to original ordering
            return results[: (top_k or settings.rerank_top_k)]

    async def rerank_async(
        self,
        query: str,
        results: List[RerankedResult],
        top_k: int | None = None,
    ) -> List[RerankedResult]:
        """Async version of rerank (runs in thread pool).

        Args:
            query: Search query
            results: List of results to rerank
            top_k: Number of top results to return

        Returns:
            Reranked list of results
        """
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.rerank(query, results, top_k))


class NoOpReranker:
    """Reranker that doesn't rerank (for testing or when disabled)."""

    def rerank(
        self,
        query: str,
        results: List[RerankedResult],
        top_k: int | None = None,
    ) -> List[RerankedResult]:
        """Return results unchanged, limited to top_k."""
        k = top_k or settings.rerank_top_k
        return results[:k]

    async def rerank_async(
        self,
        query: str,
        results: List[RerankedResult],
        top_k: int | None = None,
    ) -> List[RerankedResult]:
        """Async version - just calls sync version."""
        return self.rerank(query, results, top_k)


def get_reranker() -> CrossEncoderReranker | NoOpReranker:
    """Factory function to get appropriate reranker."""
    if settings.rerank_results:
        return CrossEncoderReranker()
    else:
        return NoOpReranker()
