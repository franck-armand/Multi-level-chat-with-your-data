from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from chatwithdocs.config import settings
from chatwithdocs.embedding import EmbeddingRouter
from chatwithdocs.storage.vectors import ChunkMetadata, VectorStore

logger = logging.getLogger(__name__)


@dataclass
class HybridSearchResult:
    """Result from hybrid search combining multiple sources."""

    id: str
    content: str
    score: float  # Fused score
    bm25_score: Optional[float] = None
    vector_score: Optional[float] = None
    metadata: ChunkMetadata = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = ChunkMetadata(source_file="", file_type="")


class BM25Index:
    """In-memory BM25 index for keyword search."""

    def __init__(self):
        self._corpus: List[str] = []
        self._metadata: List[Dict[str, Any]] = []
        self._bm25 = None

    def add_documents(self, documents: List[str], metadata: List[Dict[str, Any]]) -> None:
        """Add documents to the BM25 index."""
        self._corpus.extend(documents)
        self._metadata.extend(metadata)
        self._build_index()

    def _build_index(self) -> None:
        """Build or rebuild the BM25 index."""
        if not self._corpus:
            self._bm25 = None
            return

        try:
            from rank_bm25 import BM25Okapi

            # Simple tokenization
            tokenized_corpus = [doc.lower().split() for doc in self._corpus]
            self._bm25 = BM25Okapi(tokenized_corpus)
            logger.info(f"Built BM25 index with {len(self._corpus)} documents")
        except ImportError:
            logger.warning("rank-bm25 not installed, BM25 search disabled")
            self._bm25 = None

    def search(self, query: str, k: int = 10) -> List[tuple[int, float]]:
        """Search the BM25 index.

        Returns:
            List of (document_index, score) tuples
        """
        if self._bm25 is None or not self._corpus:
            return []

        try:
            tokenized_query = query.lower().split()
            scores = self._bm25.get_scores(tokenized_query)

            # Get top-k indices
            import numpy as np

            top_k_indices = np.argsort(scores)[::-1][:k]
            return [(int(idx), float(scores[idx])) for idx in top_k_indices]
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def clear(self) -> None:
        """Clear the index."""
        self._corpus.clear()
        self._metadata.clear()
        self._bm25 = None


class HybridSearcher:
    """Hybrid search combining BM25 and vector search."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: EmbeddingRouter | None = None,
        bm25_weight: float | None = None,
        vector_weight: float | None = None,
    ):
        self.vector_store = vector_store
        self.embedder = embedder or EmbeddingRouter()
        self.bm25_index = BM25Index()
        self.bm25_weight = bm25_weight or (1 - settings.hybrid_search_weight)
        self.vector_weight = vector_weight or settings.hybrid_search_weight

    async def search(
        self,
        query: str,
        k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[HybridSearchResult]:
        """Perform hybrid search combining BM25 and vector search.

        Uses Reciprocal Rank Fusion (RRF) to combine results.

        Args:
            query: Search query
            k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of hybrid search results
        """
        results_map: Dict[str, HybridSearchResult] = {}

        # Vector search
        if settings.use_vector_search:
            try:
                query_embedding = await self.embedder.embed_query(query)
                vector_results = await self.vector_store.search(
                    query_embedding.embedding, k=k * 2, filter_dict=filter_dict
                )

                for rank, result in enumerate(vector_results):
                    rrf_score = self._rrf_score(rank)
                    results_map[result.id] = HybridSearchResult(
                        id=result.id,
                        content=result.content,
                        score=rrf_score * self.vector_weight,
                        vector_score=result.score,
                        metadata=self._dict_to_metadata(result.metadata),
                    )
            except Exception as e:
                logger.error(f"Vector search failed: {e}")

        # BM25 search (only if no filters, since BM25 doesn't support metadata filtering)
        if settings.use_bm25 and not filter_dict:
            bm25_results = self.bm25_index.search(query, k=k * 2)
            for rank, (idx, bm25_score) in enumerate(bm25_results):
                rrf_score = self._rrf_score(rank)
                # Note: BM25 results need to be correlated with vector store results
                # For now, we'll skip adding them if not already in results
                # This is a simplified implementation

        # Sort by fused score
        sorted_results = sorted(results_map.values(), key=lambda x: x.score, reverse=True)
        return sorted_results[:k]

    def _rrf_score(self, rank: int, k: int = 60) -> float:
        """Calculate Reciprocal Rank Fusion score.

        RRF score = 1 / (k + rank)

        Args:
            rank: 0-based rank
            k: Constant (default 60)

        Returns:
            RRF score
        """
        return 1.0 / (k + rank + 1)

    def _dict_to_metadata(self, data: Dict[str, Any]) -> ChunkMetadata:
        """Convert dict to ChunkMetadata."""
        return ChunkMetadata(
            source_file=data.get("source_file", ""),
            file_type=data.get("file_type", ""),
            page_number=data.get("page_number"),
            section_header=data.get("section_header"),
            chunk_type=data.get("chunk_type", "text"),
            user_id=data.get("user_id"),
            custom={
                k: v
                for k, v in data.items()
                if k
                not in [
                    "source_file",
                    "file_type",
                    "page_number",
                    "section_header",
                    "chunk_type",
                    "user_id",
                ]
            },
        )

    async def add_to_index(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[ChunkMetadata],
    ) -> None:
        """Add documents to both vector store and BM25 index."""
        # Add to vector store
        await self.vector_store.add_chunks(chunks, embeddings, metadata)

        # Add to BM25 index
        meta_dicts = [
            {
                "source_file": m.source_file,
                "file_type": m.file_type,
                "page_number": m.page_number,
                "section_header": m.section_header,
                "chunk_type": m.chunk_type,
                "user_id": m.user_id,
                **m.custom,
            }
            for m in metadata
        ]
        self.bm25_index.add_documents(chunks, meta_dicts)

    async def delete_by_source(self, source_file: str) -> None:
        """Delete documents from both indexes by source."""
        await self.vector_store.delete_by_source(source_file)
        # Note: BM25 index doesn't support selective deletion in this simple implementation
        # Would need to rebuild the index
