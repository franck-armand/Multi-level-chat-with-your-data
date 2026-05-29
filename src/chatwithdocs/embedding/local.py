from __future__ import annotations

import logging
from typing import Any, List

from chatwithdocs.config import settings
from chatwithdocs.embedding.base import BaseEmbedder, EmbeddingResult

logger = logging.getLogger(__name__)


class LocalEmbedder(BaseEmbedder):
    """Local embedding provider using sentence-transformers.

    This embedder runs locally without requiring API keys.
    Uses CPU by default, can use GPU if available.
    """

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
    ):
        self.model_name = model_name or settings.local_embedding_model
        self.device = device or settings.local_embedding_device
        self._model: Any | None = None
        self._dimension: int | None = None

    def _load_model(self):
        """Lazy load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer

                logger.info(f"Loading local embedding model: {self.model_name}")
                self._model = SentenceTransformer(self.model_name, device=self.device)
                self._dimension = self._model.get_sentence_embedding_dimension()
                logger.info(f"Model loaded. Dimension: {self._dimension}")
            except ImportError:
                raise ImportError(
                    "sentence-transformers not installed. "
                    "Install with: uv pip install sentence-transformers"
                )
            except Exception as e:
                logger.error(f"Failed to load embedding model: {e}")
                raise

    async def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed texts using local model.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding results
        """
        self._load_model()

        # Handle empty input
        if not texts:
            return []

        # Encode texts (this is CPU-bound, run in thread pool if needed)
        import asyncio
        from typing import cast

        model = cast(Any, self._model)
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, lambda: model.encode(texts, show_progress_bar=False)
        )

        return [
            EmbeddingResult(
                text=text,
                embedding=embedding.tolist(),
                model=self.model_name,
            )
            for text, embedding in zip(texts, embeddings)
        ]

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        if self._dimension is None:
            self._load_model()
        return self._dimension  # type: ignore[return-value]

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model_name
