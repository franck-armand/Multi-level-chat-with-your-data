from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, ClassVar, Dict, List, Optional

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


@dataclass
class BM25SearchResult:
    """Result from BM25 keyword search."""

    id: str
    content: str
    score: float
    metadata: Dict[str, Any]


class BM25Index:
    """In-memory BM25 index for keyword search."""

    _shared_indices: ClassVar[dict[str, "BM25Index"]] = {}

    def __init__(self):
        self._ids: List[str] = []
        self._corpus: List[str] = []
        self._metadata: List[Dict[str, Any]] = []
        self._bm25 = None

    @classmethod
    def shared(cls, namespace: str) -> "BM25Index":
        """Get or create a shared BM25 index for a namespace."""
        if namespace not in cls._shared_indices:
            cls._shared_indices[namespace] = cls()
        return cls._shared_indices[namespace]

    @classmethod
    def clear_shared(cls) -> None:
        """Clear all shared BM25 indices."""
        cls._shared_indices.clear()

    def add_documents(
        self, documents: List[str], metadata: List[Dict[str, Any]], ids: List[str]
    ) -> None:
        """Add documents to the BM25 index."""
        self._ids.extend(ids)
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

    def search(
        self,
        query: str,
        k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[BM25SearchResult]:
        """Search the BM25 index.

        Returns:
            List of BM25 search results
        """
        if self._bm25 is None or not self._corpus:
            return []

        try:
            tokenized_query = query.lower().split()
            scores = self._bm25.get_scores(tokenized_query)

            import numpy as np

            ranked_indices = np.argsort(scores)[::-1]
            results: List[BM25SearchResult] = []
            for idx in ranked_indices:
                index = int(idx)
                metadata = self._metadata[index]
                if filter_dict and not self._matches_filter(metadata, filter_dict):
                    continue

                results.append(
                    BM25SearchResult(
                        id=self._ids[index],
                        content=self._corpus[index],
                        score=float(scores[index]),
                        metadata=metadata,
                    )
                )
                if len(results) >= k:
                    break
            return results
        except Exception as e:
            logger.error(f"BM25 search failed: {e}")
            return []

    def delete(self, filter_dict: Dict[str, Any]) -> int:
        """Delete indexed documents matching a metadata filter."""
        keep_indices = [
            idx
            for idx, metadata in enumerate(self._metadata)
            if not self._matches_filter(metadata, filter_dict)
        ]
        deleted = len(self._metadata) - len(keep_indices)
        if deleted == 0:
            return 0

        self._ids = [self._ids[idx] for idx in keep_indices]
        self._corpus = [self._corpus[idx] for idx in keep_indices]
        self._metadata = [self._metadata[idx] for idx in keep_indices]
        self._build_index()
        return deleted

    def _matches_filter(self, metadata: Dict[str, Any], filter_dict: Dict[str, Any]) -> bool:
        """Check whether stored metadata matches a filter dict."""
        for key, expected in filter_dict.items():
            actual = metadata.get(key)
            if isinstance(expected, dict):
                for operator, value in expected.items():
                    if operator == "$eq" and actual != value:
                        return False
                    if operator == "$in" and actual not in value:
                        return False
                    if operator == "$gte" and (actual is None or actual < value):
                        return False
                    if operator == "$lte" and (actual is None or actual > value):
                        return False
            elif actual != expected:
                return False
        return True

    def clear(self) -> None:
        """Clear the index."""
        self._ids.clear()
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
        namespace = getattr(vector_store, "collection_name", vector_store.__class__.__name__)
        self.bm25_index = BM25Index.shared(namespace)
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

        if settings.use_bm25:
            bm25_results = self.bm25_index.search(query, k=k * 2, filter_dict=filter_dict)
            for rank, bm25_result in enumerate(bm25_results):
                rrf_score = self._rrf_score(rank)
                existing = results_map.get(bm25_result.id)
                if existing:
                    existing.score += rrf_score * self.bm25_weight
                    existing.bm25_score = bm25_result.score
                    continue

                results_map[bm25_result.id] = HybridSearchResult(
                    id=bm25_result.id,
                    content=bm25_result.content,
                    score=rrf_score * self.bm25_weight,
                    bm25_score=bm25_result.score,
                    metadata=self._dict_to_metadata(bm25_result.metadata),
                )

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
    ) -> List[str]:
        """Add documents to both vector store and BM25 index."""
        # Add to vector store
        ids = await self.vector_store.add_chunks(chunks, embeddings, metadata)

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
        self.bm25_index.add_documents(chunks, meta_dicts, ids)
        return ids

    async def delete_by_source(self, source_file: str) -> None:
        """Delete documents from both indexes by source."""
        await self.vector_store.delete_by_source(source_file)
        self.bm25_index.delete({"source_file": source_file})

    async def delete_by_user(self, user_id: str) -> int:
        """Delete documents from both indexes by user."""
        deleted = 0
        delete_by_user = getattr(self.vector_store, "delete_by_user", None)
        if callable(delete_by_user):
            deleted = await delete_by_user(user_id)
        self.bm25_index.delete({"user_id": user_id})
        return deleted
