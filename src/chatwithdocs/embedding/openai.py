from __future__ import annotations

import logging
from typing import List

from chatwithdocs.config import settings
from chatwithdocs.embedding.base import BaseEmbedder, EmbeddingResult

logger = logging.getLogger(__name__)


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI API embedding provider.

    Requires OPENAI_API_KEY environment variable or setting.
    Supports both OpenAI and OpenAI-compatible APIs (DeepSeek, etc.)
    """

    DIMENSIONS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
        "text-embedding-ada-002": 1536,
    }

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url or settings.openai_base_url
        self.model = model or settings.openai_embedding_model
        self._client = None

    def _get_client(self):
        """Lazy initialize OpenAI client."""
        if self._client is None:
            if not self.api_key:
                raise ValueError(
                    "OpenAI API key not configured. "
                    "Set OPENAI_API_KEY environment variable or configure in settings."
                )

            try:
                import openai

                api_key = self.api_key
                if not isinstance(api_key, str):
                    raise ValueError("API key must be a string")

                if self.base_url:
                    base_url = self.base_url
                    if not isinstance(base_url, str):
                        raise ValueError("Base URL must be a string")
                    self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
                else:
                    self._client = openai.AsyncOpenAI(api_key=api_key)
                logger.info(f"OpenAI client initialized (model: {self.model})")
            except ImportError:
                raise ImportError("openai not installed. Install with: uv pip install openai")
        return self._client

    async def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed texts using OpenAI API.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding results
        """
        if not texts:
            return []

        client = self._get_client()

        try:
            response = await client.embeddings.create(
                model=self.model,
                input=texts,
            )

            return [
                EmbeddingResult(
                    text=text,
                    embedding=data.embedding,
                    model=self.model,
                )
                for text, data in zip(texts, response.data)
            ]
        except Exception as e:
            logger.error(f"OpenAI embedding failed: {e}")
            raise

    def get_dimension(self) -> int:
        """Get embedding dimension for the model."""
        return self.DIMENSIONS.get(self.model, 1536)

    def get_model_name(self) -> str:
        """Get model name."""
        return self.model
