from __future__ import annotations

from chatwithdocs.embedding.base import BaseEmbedder, EmbeddingResult
from chatwithdocs.embedding.local import LocalEmbedder
from chatwithdocs.embedding.openai import OpenAIEmbedder
from chatwithdocs.embedding.router import EmbeddingRouter

__all__ = [
    "BaseEmbedder",
    "EmbeddingResult",
    "LocalEmbedder",
    "OpenAIEmbedder",
    "EmbeddingRouter",
]
