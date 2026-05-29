from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List


@dataclass
class EmbeddingResult:
    """Result of embedding operation."""

    text: str
    embedding: List[float]
    model: str


class BaseEmbedder(ABC):
    """Abstract base class for embedding providers."""

    @abstractmethod
    async def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed a list of texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding results
        """
        pass

    @abstractmethod
    def get_dimension(self) -> int:
        """Get the dimension of embeddings produced by this model."""
        pass

    @abstractmethod
    def get_model_name(self) -> str:
        """Get the name of the embedding model."""
        pass

    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query text.

        Args:
            query: Query text to embed

        Returns:
            Single embedding result
        """
        results = await self.embed([query])
        return results[0]
