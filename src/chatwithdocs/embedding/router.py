from __future__ import annotations

import logging
from typing import List

from chatwithdocs.config import settings, EmbeddingProvider
from chatwithdocs.embedding.base import BaseEmbedder, EmbeddingResult
from chatwithdocs.embedding.local import LocalEmbedder

logger = logging.getLogger(__name__)


class EmbeddingRouter(BaseEmbedder):
    """Router that automatically selects the best embedding provider.

    Selection order:
    1. If provider is explicitly set to "local", use LocalEmbedder
    2. If provider is "openai" and API key is available, use OpenAIEmbedder
    3. If provider is "auto", try OpenAI first (better quality), fall back to local
    4. If OpenAI fails or no key, fall back to LocalEmbedder
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        fallback_on_error: bool = True,
    ):
        self.provider = provider or settings.embedding_provider
        self.fallback_on_error = fallback_on_error
        self._primary: BaseEmbedder | None = None
        self._fallback: BaseEmbedder | None = None

    def _initialize_providers(self):
        """Initialize primary and fallback providers."""
        if self._primary is not None:
            return

        if self.provider == EmbeddingProvider.LOCAL:
            logger.info("Using local embedding provider")
            self._primary = LocalEmbedder()
            self._fallback = None

        elif self.provider == EmbeddingProvider.OPENAI:
            from chatwithdocs.embedding.openai import OpenAIEmbedder

            if settings.openai_api_key:
                logger.info("Using OpenAI embedding provider")
                self._primary = OpenAIEmbedder()
                self._fallback = LocalEmbedder() if self.fallback_on_error else None
            else:
                logger.warning(
                    "OpenAI provider requested but no API key found. "
                    "Falling back to local provider."
                )
                self._primary = LocalEmbedder()
                self._fallback = None

        elif self.provider == EmbeddingProvider.AUTO:
            # Try OpenAI first, fall back to local
            if settings.openai_api_key:
                from chatwithdocs.embedding.openai import OpenAIEmbedder

                logger.info("Auto mode: Using OpenAI as primary, local as fallback")
                self._primary = OpenAIEmbedder()
                self._fallback = LocalEmbedder()
            else:
                logger.info("Auto mode: No OpenAI key, using local provider")
                self._primary = LocalEmbedder()
                self._fallback = None

    async def embed(self, texts: List[str]) -> List[EmbeddingResult]:
        """Embed texts using selected provider with optional fallback.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding results
        """
        self._initialize_providers()

        try:
            return await self._primary.embed(texts)
        except Exception as e:
            if self._fallback and self.fallback_on_error:
                logger.warning(f"Primary embedder failed ({e}), using fallback")
                return await self._fallback.embed(texts)
            raise

    async def embed_query(self, query: str) -> EmbeddingResult:
        """Embed a single query with fallback support."""
        self._initialize_providers()

        try:
            return await self._primary.embed_query(query)
        except Exception as e:
            if self._fallback and self.fallback_on_error:
                logger.warning(f"Primary embedder failed ({e}), using fallback")
                return await self._fallback.embed_query(query)
            raise

    def get_dimension(self) -> int:
        """Get dimension from primary provider."""
        self._initialize_providers()
        return self._primary.get_dimension()

    def get_model_name(self) -> str:
        """Get model name from primary provider."""
        self._initialize_providers()
        return self._primary.get_model_name()

    def get_active_provider(self) -> str:
        """Get the name of currently active provider."""
        self._initialize_providers()
        return self._primary.get_model_name()
