from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


class LangfuseClient:
    """Langfuse observability client for tracing and scoring RAG pipelines.

    Uses Langfuse SDK v4 API.
    """

    def __init__(self):
        self._client = None
        self._enabled = False

    def _ensure_client(self):
        """Lazy initialization of Langfuse client."""
        if self._client is not None:
            return

        if not settings.langfuse_enabled:
            logger.debug("Langfuse disabled in settings")
            return

        if not settings.langfuse_secret_key or not settings.langfuse_public_key:
            logger.warning("Langfuse keys not configured")
            return

        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_base_url,
            )
            self._enabled = True
            logger.info(f"Langfuse initialized: {settings.langfuse_base_url}")
        except ImportError:
            logger.warning("langfuse package not installed")
        except Exception as e:
            logger.error(f"Failed to initialize Langfuse: {e}")

    @property
    def enabled(self) -> bool:
        """Check if Langfuse is enabled and connected."""
        if not self._enabled:
            self._ensure_client()
        return self._enabled

    def _make_trace_id(self, thread_id: str | None, user_id: str) -> str:
        """Create a valid 32-char hex trace_id from thread_id or user_id."""
        import hashlib

        raw = thread_id if thread_id else user_id
        hash_obj = hashlib.md5(raw.encode())
        return hash_obj.hexdigest()

    def trace_generation(
        self,
        user_id: str,
        query: str,
        answer: str,
        thread_id: str | None = None,
        metadata: dict | None = None,
    ) -> str | None:
        """Trace a generation run in Langfuse using v4 API with proper session support."""
        if not self.enabled:
            return None

        try:
            from langfuse import propagate_attributes

            langfuse = self._client

            session_key = thread_id if thread_id else user_id
            trace_id = self._make_trace_id(thread_id, user_id)

            obs_metadata = {
                "user_id": user_id,
                "type": "generation",
                **(metadata or {}),
            }

            with propagate_attributes(session_id=session_key):
                obs = langfuse.start_observation(
                    trace_context={"trace_id": trace_id},
                    name="chat",
                    input={"query": query},
                    metadata=obs_metadata,
                )
                obs.update(output={"answer": answer})
                obs.end()

            logger.info(f"Langfuse trace logged for user {user_id}, session {session_key}")
            return f"{settings.langfuse_base_url}/traces?sessionId={session_key}"
        except Exception as e:
            logger.warning(f"Langfuse trace skipped: {e}")
            return None

    def trace_retrieval(
        self,
        query: str,
        chunks: list[dict[str, Any]],
        scores: list[float] | None = None,
    ) -> str | None:
        """Trace a retrieval run."""
        if not self.enabled:
            return None

        try:
            langfuse = self._client

            with langfuse.start_as_current_observation(
                name="retrieval",
                input={"query": query, "k": len(chunks)},
                metadata={"retrieved_chunks": len(chunks)},
            ):
                pass

            return "logged"
        except Exception as e:
            logger.error(f"Failed to trace retrieval: {e}")
            return None

    def trace_reranking(
        self,
        query: str,
        input_chunks: int,
        output_chunks: list[dict[str, Any]],
    ) -> str | None:
        """Trace a reranking run."""
        if not self.enabled:
            return None

        try:
            langfuse = self._client

            with langfuse.start_as_current_observation(
                name="reranking",
                input={"query": query, "input_k": input_chunks, "output_k": len(output_chunks)},
                metadata={"reranked": True},
            ):
                pass

            return "logged"
        except Exception as e:
            logger.error(f"Failed to trace reranking: {e}")
            return None

    @contextmanager
    def trace_span(
        self,
        name: str,
        metadata: dict | None = None,
    ):
        """Context manager for tracing a span (e.g., ingestion, full pipeline)."""
        if not self.enabled:
            yield None
            return

        try:
            langfuse = self._client

            with langfuse.start_as_current_observation(name=name, metadata=metadata or {}) as span:
                yield span
        except Exception as e:
            logger.error(f"Failed to create span: {e}")
            yield None

    def score_generation(
        self,
        trace_id: str,
        name: str,
        value: float,
        comment: str | None = None,
    ) -> bool:
        """Score a generation (e.g., RAGAS metrics)."""
        if not self.enabled:
            return False

        try:

            langfuse = self._client

            langfuse.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to score: {e}")
            return False


# Global client instance
langfuse_client = LangfuseClient()