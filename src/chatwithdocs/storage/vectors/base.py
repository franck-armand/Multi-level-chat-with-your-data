from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SearchResult:
    """Result from vector search."""

    id: str
    content: str
    score: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkMetadata:
    """Metadata for a chunk in the vector store."""

    source_file: str
    file_type: str
    page_number: Optional[int] = None
    section_header: Optional[str] = None
    chunk_type: str = "text"
    user_id: Optional[str] = None
    doc_id: Optional[str] = None
    custom: Dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """Abstract base class for vector storage backends."""

    @abstractmethod
    async def add_chunks(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[ChunkMetadata],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Add chunks with embeddings to the store.

        Args:
            chunks: List of text chunks
            embeddings: List of embedding vectors
            metadata: List of metadata for each chunk
            ids: Optional list of IDs (auto-generated if not provided)

        Returns:
            List of IDs for added chunks
        """
        pass

    @abstractmethod
    async def search(
        self,
        query_embedding: List[float],
        k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for similar chunks.

        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of search results
        """
        pass

    @abstractmethod
    async def delete_by_source(self, source_file: str) -> int:
        """Delete all chunks from a source file.

        Args:
            source_file: Source file path

        Returns:
            Number of chunks deleted
        """
        pass

    @abstractmethod
    async def delete_by_id(self, chunk_id: str) -> bool:
        """Delete a chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics.

        Returns:
            Dictionary with stats (total_chunks, etc.)
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all data from the store."""
        pass

    async def health_check(self) -> bool:
        """Check if the store is healthy.

        Returns:
            True if healthy
        """
        try:
            await self.get_stats()
            return True
        except Exception:
            return False
