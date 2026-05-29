from __future__ import annotations

import logging
import re
import unicodedata
import time
from dataclasses import dataclass
from typing import List, Optional

from chatwithdocs.chat.manager import ConversationManager
from chatwithdocs.chat.models import Citation, MessageRole, Thread
from chatwithdocs.config import settings
from chatwithdocs.embedding import EmbeddingRouter
from chatwithdocs.llm.client import LLMMessage, LLMRouter
from chatwithdocs.obs.langfuse import langfuse_client
from chatwithdocs.obs.sinks import JsonlTraceSink
from chatwithdocs.obs.trace import Trace, TraceEvent, new_trace, trace_event
from chatwithdocs.retrieval import HybridSearcher, get_reranker
from chatwithdocs.retrieval.citation import CitationBuilder
from chatwithdocs.retrieval.confidence import ConfidenceScorer
from chatwithdocs.retrieval.hybrid_search import HybridSearchResult
from chatwithdocs.retrieval.query_validator import QueryValidator
from chatwithdocs.storage.vectors import ChromaVectorStore

logger = logging.getLogger(__name__)

SMALLTALK_ONLY_PATTERNS = {
    "hello",
    "hi",
    "hey",
    "good morning",
    "good afternoon",
    "good evening",
    "how are you",
    "how are you doing",
    "thanks",
    "thank you",
    "thank you very much",
    "bonjour",
    "salut",
    "bonsoir",
    "coucou",
    "ca va",
    "comment ca va",
    "merci",
    "merci beaucoup",
    "yo",
    "greetings",
    "good day",
    "nice to meet you",
    "pleased to meet you",
}

SMALLTALK_TOKENS = {
    "hello",
    "hi",
    "hey",
    "bonjour",
    "salut",
    "bonsoir",
    "coucou",
    "thanks",
    "thank",
    "merci",
}

DOCUMENT_HINTS = {
    "document",
    "doc",
    "file",
    "pdf",
    "csv",
    "contract",
    "report",
    "agreement",
    "upload",
    "uploaded",
    "page",
    "section",
    "clause",
    "article",
    "documento",
    "fichier",
    "contrat",
    "rapport",
    "piece",
    "pieces",
    "televerse",
    "uploades",
    "page",
    "section",
    "clause",
    "article",
}

QUESTION_HINTS = {
    "what",
    "which",
    "where",
    "when",
    "why",
    "how",
    "who",
    "does",
    "do",
    "can",
    "could",
    "please",
    "que",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "ou",
    "quand",
    "pourquoi",
    "comment",
    "est ce",
    "peux",
    "peut",
    "montre",
    "resume",
    "explique",
}

ALLOWED_QUERY_INTENTS = {"smalltalk", "document_question", "mixed"}
FRENCH_LANGUAGE_HINTS = {
    "bonjour",
    "salut",
    "bonsoir",
    "coucou",
    "merci",
    "contrat",
    "rapport",
    "fichier",
    "document",
    "quel",
    "quelle",
    "quels",
    "quelles",
    "comment",
    "pourquoi",
    "quand",
    "peux",
    "peut",
    "montre",
    "resume",
    "explique",
    "page",
    "section",
}
VAGUE_QUERY_PATTERNS = (
    "what about this",
    "what about that",
    "and this",
    "and that",
    "this one",
    "that one",
    "tell me more",
    "can you elaborate",
    "et celui ci",
    "et celle ci",
    "et ca",
    "et ceci",
    "ce document",
    "ce fichier",
)


@dataclass
class AnswerabilityDecision:
    """Decision produced by the retrieval-quality gate."""

    status: str
    reason: str
    confidence: float


class ChatEngine:
    """Main chat engine orchestrating retrieval and response generation.

    This is the core component that:
    1. Retrieves relevant context from vector store
    2. Reranks results for better relevance
    3. Builds citations for sources
    4. Generates responses (local or via LLM)
    """

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedder: EmbeddingRouter | None = None,
        conversation_manager: ConversationManager | None = None,
    ):
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedder = embedder or EmbeddingRouter()
        self.conversation_manager = conversation_manager or ConversationManager()
        self.hybrid_searcher = HybridSearcher(self.vector_store, self.embedder)
        self.reranker = get_reranker()
        self.citation_builder = CitationBuilder()
        self.confidence_scorer = ConfidenceScorer()
        self.query_validator = QueryValidator()

    async def chat(
        self,
        user_id: str,
        thread_id: str | None,
        message: str,
    ) -> dict:
        """Process a chat message and generate a response.

        Args:
            user_id: User identifier
            thread_id: Thread ID (creates new if None)
            message: User message

        Returns:
            Response dictionary with content and citations
        """
        # Validate query
        is_valid, error = self.query_validator.validate(message)
        if not is_valid:
            raise ValueError(error)

        # Get or create thread
        if thread_id:
            thread = self.conversation_manager.get_thread(thread_id)
            if not thread or thread.user_id != user_id:
                thread = self.conversation_manager.create_thread(user_id)
        else:
            thread = self.conversation_manager.create_thread(user_id)

        # Add user message
        self.conversation_manager.add_user_message(thread.id, message)
        trace = self._new_chat_trace(user_id, thread.id, message)

        with trace_event(trace, "chat.intent.resolve", {"message_length": len(message)}):
            intent = await self._resolve_query_intent(message)
        logger.debug(f"Intent resolved for query '{message[:30]}...': {intent}")
        self._record_trace_event(
            trace,
            "chat.intent.result",
            {
                "intent": intent,
                "language": self._detect_response_language(message),
                "query_preview": message[:50],
            },
        )
        search_results = []
        if intent != "smalltalk":
            # Retrieve context (filtered by user_id)
            with trace_event(trace, "chat.retrieve", {"k": 10}):
                search_results = await self._retrieve_context(message, user_id)
        self._record_trace_event(
            trace,
            "chat.retrieve.result",
            self._build_retrieval_trace_data(search_results),
        )

        # Rerank if enabled
        if settings.rerank_results and search_results:
            from chatwithdocs.retrieval.reranker import RerankedResult

            with trace_event(trace, "chat.rerank", {"input_results": len(search_results)}):
                rerank_inputs = [
                    RerankedResult(
                        id=r.id,
                        content=r.content,
                        score=r.score,
                        original_score=r.score,
                        metadata={
                            "source_file": r.metadata.source_file,
                            "page_number": r.metadata.page_number,
                            "section": r.metadata.section_header,
                        },
                    )
                    for r in search_results
                ]
                reranked = await self.reranker.rerank_async(message, rerank_inputs)

            # Update search_results order based on reranking
            reranked_ids = {r.id: i for i, r in enumerate(reranked)}
            search_results.sort(key=lambda x: reranked_ids.get(x.id, 999))
            self._record_trace_event(
                trace,
                "chat.rerank.result",
                {
                    "returned_results": len(reranked),
                    "top_rerank_scores": [round(result.score, 6) for result in reranked[:3]],
                },
            )

        answerability = self._assess_answerability(message, search_results, intent)
        self._record_trace_event(
            trace,
            "chat.answerability",
            self._build_answerability_trace_data(message, search_results, intent, answerability),
        )

        # Build citations
        citation_data = [(r.id, r.content, r.metadata, r.score) for r in search_results]
        citations = self.citation_builder.build_citations(citation_data)

        # Generate response
        response_content = await self._generate_response(
            message,
            search_results,
            citations,
            thread,
            intent=intent,
            answerability=answerability,
        )
        self._record_trace_event(
            trace,
            "chat.response",
            {
                "intent": intent,
                "answerability_status": answerability.status,
                "response_length": len(response_content),
                "citation_count": len(citations),
            },
        )
        self._write_chat_trace(trace)

        # Calculate confidence score
        confidence = self.confidence_scorer.score(
            query=message,
            retrieval_results=search_results,
            response=response_content,
            intent=intent,
        )

        # Trace to Langfuse for observability with session support
        if langfuse_client.enabled:
            langfuse_metadata = {
                "intent": intent,
                "answerability_status": answerability.status,
                "retrieved_chunks": len(search_results),
                "citations": len(citations),
                "confidence_score": round(confidence.score, 3),
                "confidence_factors": {k: round(v, 3) for k, v in confidence.factors.items()},
            }
            if search_results:
                langfuse_metadata["top_retrieval_score"] = search_results[0].score if search_results else 0.0
            try:
                trace_url = langfuse_client.trace_generation(
                    user_id=user_id,
                    query=message,
                    answer=response_content,
                    thread_id=thread.id,
                    metadata=langfuse_metadata,
                )
                logger.info(f"Langfuse trace: {trace_url}")
            except Exception as e:
                logger.error(f"Langfuse trace failed: {e}")

        # Add assistant message
        self.conversation_manager.add_assistant_message(thread.id, response_content, citations)

        # Auto-generate thread title if this is the first message
        if len(thread.messages) <= 2 and (not thread.title or thread.title == "New Chat"):
            await self._auto_generate_title(thread, message)

        return {
            "thread_id": thread.id,
            "content": response_content,
            "citations": [c.to_dict() for c in citations],
            "sources": list(set(c.source_file for c in citations)),
            "confidence": {
                "score": round(confidence.score, 3),
                "factors": {k: round(v, 3) for k, v in confidence.factors.items()},
                "reasoning": confidence.reasoning,
            },
        }

    async def _auto_generate_title(self, thread: Thread, first_message: str) -> None:
        """Auto-generate a chat title from the first user message.

        Similar to ChatGPT, creates a concise 3-5 word title.

        Args:
            thread: The chat thread
            first_message: First user message
        """
        # Generate a short title using the LLM
        try:
            from chatwithdocs.llm.client import LLMMessage, LLMRouter

            router = LLMRouter()
            messages = [
                LLMMessage(
                    role="system",
                    content="You are a helpful assistant that creates very short chat titles. "
                    "Given a user's first message, create a concise 3-5 word title that summarizes the topic. "
                    "Be specific but brief. Output ONLY the title, nothing else.",
                ),
                LLMMessage(
                    role="user",
                    content=f"Create a short 3-5 word title for this chat:\n{first_message[:200]}",
                ),
            ]

            response = await router.generate(messages, temperature=0.3, max_tokens=20)

            if response.content and not response.error:
                # Clean up the title
                title = response.content.strip().strip('"').strip("'")
                # Limit to 40 chars
                title = title[:40] if len(title) > 40 else title
                if title:
                    thread.title = title
                    # Update in database
                    self.conversation_manager.persistence.update_thread(thread)
        except Exception as e:
            # Silently fail - not critical
            logger.debug(f"Failed to auto-generate title: {e}")

    async def _retrieve_context(
        self, query: str, user_id: str, k: int = 10
    ) -> List[HybridSearchResult]:
        """Retrieve relevant context using hybrid search (filtered by user).

        Args:
            query: Search query
            user_id: User ID to filter results
            k: Number of results to retrieve

        Returns:
            List of search results for this user only
        """
        try:
            # Filter by user_id to prevent cross-user data leakage
            filter_dict = {"user_id": user_id}
            results = await self.hybrid_searcher.search(query, k=k, filter_dict=filter_dict)
            logger.debug(f"Retrieved {len(results)} results for user {user_id}: {query[:50]}...")
            return results
        except Exception as e:
            logger.error(f"Context retrieval failed for user {user_id}: {e}")
            return []

    async def _generate_response(
        self,
        query: str,
        search_results: List,
        citations: List[Citation],
        thread: Thread,
        intent: str = "document_question",
        answerability: AnswerabilityDecision | None = None,
    ) -> str:
        """Generate a response based on retrieved context using LLM.

        Args:
            query: User query
            search_results: Retrieved search results
            citations: Built citations
            thread: Conversation thread

        Returns:
            Generated response text
        """
        language = self._detect_response_language(query)
        if intent == "smalltalk":
            return self._build_smalltalk_response(language)

        if answerability and answerability.status == "needs_clarification":
            return self._build_clarification_response(language)

        if answerability and answerability.status == "not_grounded":
            return self._build_low_evidence_response(language)

        if not search_results:
            if intent == "mixed":
                return (
                    f"{self._build_smalltalk_response(language)} "
                    f"{self._build_missing_support_for_mixed_response(language)}"
                )
            return self._build_not_grounded_response(language)

        # Build context from search results (without source numbers to avoid confusion)
        # Clean up the content - remove checkboxes and extra formatting
        context_parts = []
        for result in search_results[:5]:
            content = result.content
            # Clean up markdown formatting that confuses the LLM
            content = content.replace("- [ ]", "-")
            content = content.replace("- [x]", "-")
            content = content.replace("- [X]", "-")
            context_parts.append(content)

        context = "\n\n".join(context_parts)

        # Build chat history for LLM
        chat_history = []
        # Include last 3 messages for context (excluding the current query)
        for msg in thread.messages[-6:-1]:
            role = "user" if msg.role == MessageRole.USER else "assistant"
            chat_history.append(LLMMessage(role=role, content=msg.content))

        # Generate response using LLM
        router = LLMRouter()

        # Better system prompt that encourages synthesis like Ollama chat
        system_prompt = (
            "You are a helpful AI assistant. Your task is to answer questions based on the provided context.\n\n"
            "IMPORTANT INSTRUCTIONS:\n"
            "1. Synthesize the information into a clear, well-structured answer\n"
            "2. Use paragraphs, bullet points, or numbered lists as appropriate\n"
            "3. Do NOT simply copy-paste the raw text from the context\n"
            "4. Do NOT include file paths, source numbers, or technical metadata\n"
            "5. Write as if you're explaining to a person, not listing raw data\n"
            "6. Focus on the key points that answer the question directly"
        )

        user_prompt = (
            f"Based on the following context, please answer this question: {query}\n\n"
            f"Context:\n{context}\n\n"
            f"Please provide a comprehensive but concise answer that synthesizes the information above."
        )

        messages = [
            LLMMessage(role="system", content=system_prompt),
            *chat_history,
            LLMMessage(role="user", content=user_prompt),
        ]

        response = await router.generate(messages, temperature=0.3, max_tokens=1500)

        if response.error:
            logger.error(f"LLM generation error: {response.error}")
            # Fallback to deterministic response
            return self._build_local_response(query, context, citations)

        # Post-process to clean up any remaining formatting issues
        answer = response.content
        # Remove excessive checkbox formatting if present
        answer = answer.replace("- [ ]", "- ")
        answer = answer.replace("- [x]", "- ")
        answer = answer.replace("- [X]", "- ")
        # Remove file paths if they appear
        answer = re.sub(r"data/uploads/[^\s]+/", "", answer)

        if intent == "mixed":
            answer = f"{self._build_smalltalk_response(language)} {answer}"

        return answer.strip()

    def _classify_query_intent(self, query: str) -> str:
        """Classify the query as smalltalk, document question, mixed, or ambiguous."""
        normalized = self._normalize_text(query)
        if not normalized:
            return "document_question"

        # Case-insensitive check for exact smalltalk patterns
        normalized_lower = query.strip().lower()
        if normalized_lower in {p.lower() for p in SMALLTALK_ONLY_PATTERNS}:
            return "smalltalk"

        if normalized in SMALLTALK_ONLY_PATTERNS:
            return "smalltalk"

        tokens = set(normalized.split())
        has_smalltalk = any(token in SMALLTALK_TOKENS for token in tokens)
        has_document_hint = any(token in DOCUMENT_HINTS for token in tokens)
        has_question_hint = any(token in QUESTION_HINTS for token in tokens) or "?" in query

        if has_smalltalk and (has_document_hint or has_question_hint):
            return "mixed"
        if has_smalltalk and len(tokens) <= 4:
            return "smalltalk"
        if not has_document_hint and not has_question_hint and len(tokens) <= 6:
            return "ambiguous"
        return "document_question"

    async def _resolve_query_intent(self, query: str) -> str:
        """Resolve query intent using rules first, then the model for ambiguous cases."""
        intent = self._classify_query_intent(query)
        if intent != "ambiguous":
            return intent

        model_intent = await self._classify_query_intent_with_model(query)
        if model_intent in ALLOWED_QUERY_INTENTS:
            return model_intent
        return "document_question"

    async def _classify_query_intent_with_model(self, query: str) -> str | None:
        """Use the LLM as a fallback intent classifier for ambiguous queries."""
        router = LLMRouter()
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "Classify the user's message into exactly one label: "
                    "smalltalk, document_question, or mixed. "
                    "Use smalltalk for greetings, pleasantries, or conversational openers. "
                    "Use document_question for requests that should be answered from uploaded files. "
                    "Use mixed for messages that combine smalltalk with a document request. "
                    "Reply with only the label."
                ),
            ),
            LLMMessage(role="user", content=query[:300]),
        ]

        response = await router.generate(messages, temperature=0.0, max_tokens=5)
        if response.error or not response.content:
            return None

        normalized = self._normalize_text(response.content)
        if normalized in ALLOWED_QUERY_INTENTS:
            return normalized
        return None

    def _normalize_text(self, text: str) -> str:
        """Normalize text for simple intent classification."""
        ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
        normalized = re.sub(r"[^a-z0-9\s]", " ", ascii_text.lower())
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _build_smalltalk_response(self, language: str) -> str:
        """Return a friendly conversational opener."""
        if language == "fr":
            return (
                "Bonjour ! Je suis la pour repondre a des questions sur vos documents televerses. "
                "Demandez-moi un fichier, un sujet, ou ajoutez des documents si vous voulez des reponses ancrees."
            )
        return (
            "Bonjour! Hello! I'm here to help with questions about your uploaded documents. "
            "Ask about a file, a topic inside it, or upload documents if you want grounded answers."
        )

    def _build_clarification_response(self, language: str) -> str:
        """Ask the user to narrow an underspecified document request."""
        if language == "fr":
            return (
                "J'ai besoin d'un peu plus de contexte avant de repondre a partir de vos documents. "
                "Indiquez le document, la page, la section ou le sujet que vous voulez que j'examine."
            )
        return (
            "I need a bit more context before I answer that from your documents. "
            "Please mention the document, page, section, or topic you want me to look at."
        )

    def _build_missing_support_for_mixed_response(self, language: str) -> str:
        """Return a localized mixed-intent fallback."""
        if language == "fr":
            return (
                "Je n'ai pas encore trouve assez d'informations dans vos fichiers pour la partie documentaire de votre message. "
                "Precisez le document ou le sujet que vous voulez que j'analyse, ou televersez le fichier concerne."
            )
        return (
            "I couldn't find supporting information for the document part of your message in the files you uploaded yet. "
            "Please mention the document/topic you want me to inspect, or upload the relevant file."
        )

    def _build_not_grounded_response(self, language: str) -> str:
        """Return a localized no-support response."""
        if language == "fr":
            return (
                "Je n'ai pas trouve d'informations suffisantes dans vos documents televerses pour repondre a cela. "
                "Reformulez la question, mentionnez le document ou le sujet voulu, ou ajoutez les fichiers pertinents."
            )
        return (
            "I couldn't find supporting information for that in your uploaded documents. "
            "Please rephrase the question, mention the document/topic you want, or upload relevant files."
        )

    def _build_low_evidence_response(self, language: str) -> str:
        """Return a localized weak-evidence refusal."""
        if language == "fr":
            return (
                "Je n'ai pas assez d'elements fiables dans vos documents televerses pour repondre avec confiance. "
                "Indiquez le document, la section ou le sujet que vous voulez que j'utilise."
            )
        return (
            "I don't have enough grounded evidence in your uploaded documents to answer that confidently yet. "
            "Please point me to the document, section, or topic you want me to use."
        )

    def _new_chat_trace(self, user_id: str, thread_id: str, message: str) -> Trace:
        """Create a chat trace with request metadata."""
        return new_trace(
            {
                "surface": "chat_engine",
                "user_id": user_id,
                "thread_id": thread_id,
                "message_length": len(message),
            }
        )

    def _record_trace_event(self, trace: Trace, name: str, data: dict) -> None:
        """Append an instantaneous trace event."""
        t_ms = int(time.time() * 1000)
        trace.events.append(
            TraceEvent(
                name=name,
                t0_ms=t_ms,
                t1_ms=t_ms,
                ms=0,
                data=data,
            )
        )

    def _write_chat_trace(self, trace: Trace) -> None:
        """Persist the chat trace if tracing is enabled."""
        if not settings.enable_chat_tracing:
            return

        trace.finish()
        JsonlTraceSink(settings.chat_trace_file).write(trace)

    def _build_retrieval_trace_data(self, search_results: List[HybridSearchResult]) -> dict:
        """Summarize retrieval output for tracing."""
        return {
            "result_count": len(search_results),
            "top_scores": [round(result.score, 6) for result in search_results[:3]],
            "top_sources": [result.metadata.source_file for result in search_results[:3]],
            "top_chunk_ids": [result.id for result in search_results[:3]],
        }

    def _detect_response_language(self, query: str) -> str:
        """Detect whether the guard responses should be in French or English."""
        normalized = self._normalize_text(query)
        tokens = set(normalized.split())
        if any(token in FRENCH_LANGUAGE_HINTS for token in tokens):
            return "fr"
        return "en"

    def _build_answerability_trace_data(
        self,
        query: str,
        search_results: List[HybridSearchResult],
        intent: str,
        answerability: AnswerabilityDecision,
    ) -> dict:
        """Build structured answerability diagnostics for tracing."""
        normalized_query = self._normalize_text(query)
        tokens = normalized_query.split()
        top_score = search_results[0].score if search_results else 0.0
        avg_top_scores = (
            sum(result.score for result in search_results[:3]) / min(len(search_results), 3)
            if search_results
            else 0.0
        )
        return {
            "intent": intent,
            "status": answerability.status,
            "reason": answerability.reason,
            "confidence": answerability.confidence,
            "result_count": len(search_results),
            "top_score": round(top_score, 6),
            "avg_top_3_score": round(avg_top_scores, 6),
            "has_document_hint": any(token in DOCUMENT_HINTS for token in tokens),
            "is_vague_query": any(pattern in normalized_query for pattern in VAGUE_QUERY_PATTERNS),
            "query_preview": query[:120],
        }

    def _assess_answerability(
        self,
        query: str,
        search_results: List[HybridSearchResult],
        intent: str,
    ) -> AnswerabilityDecision:
        """Heuristically decide whether the retrieved evidence is strong enough to answer."""
        if intent == "smalltalk":
            return AnswerabilityDecision(status="answerable", reason="smalltalk", confidence=1.0)

        normalized_query = self._normalize_text(query)
        tokens = normalized_query.split()
        has_document_hint = any(token in DOCUMENT_HINTS for token in tokens)
        top_score = search_results[0].score if search_results else 0.0

        is_vague = any(pattern in normalized_query for pattern in VAGUE_QUERY_PATTERNS)
        if is_vague and not has_document_hint and len(search_results) < 2:
            return AnswerabilityDecision(
                status="needs_clarification",
                reason="underspecified_query",
                confidence=0.9,
            )

        if not search_results:
            return AnswerabilityDecision(status="not_grounded", reason="no_results", confidence=1.0)

        # Lower threshold - if we have any results, try to answer
        if top_score < 0.005:
            return AnswerabilityDecision(
                status="not_grounded",
                reason="very_low_retrieval_score",
                confidence=0.95,
            )

        # Only ask for clarification if very weak evidence AND vague query
        if len(search_results) == 1 and top_score < 0.01 and is_vague:
            return AnswerabilityDecision(
                status="needs_clarification",
                reason="single_weak_result",
                confidence=0.75,
            )

        # If we have any results, assume answerable
        if search_results:
            return AnswerabilityDecision(status="answerable", reason="sufficient_evidence", confidence=0.8)

        return AnswerabilityDecision(
            status="answerable", reason="sufficient_evidence", confidence=0.8
        )

    def _build_local_response(self, query: str, context: str, citations: List[Citation]) -> str:
        """Build a local deterministic response as fallback.

        This is used when no LLM API is available. It attempts to extract
        meaningful information and present it in a readable format.

        Args:
            query: User query
            context: Retrieved context
            citations: Source citations

        Returns:
            Response text
        """
        import re

        # Clean up the context first
        # Remove checkbox formatting
        context = re.sub(r"- \[[ xX]\]\s*", "- ", context)
        # Remove file paths
        context = re.sub(r"data/uploads/[^/]+/[^\s]+/", "", context)
        # Remove extra whitespace
        context = re.sub(r"\n\s*\n", "\n\n", context)

        # Split into lines/paragraphs
        paragraphs = [p.strip() for p in context.split("\n\n") if p.strip()]

        # Try to find the most relevant paragraphs
        query_keywords = set(query.lower().split())
        scored_paragraphs = []

        for para in paragraphs[:10]:  # Check first 10 paragraphs
            para_lower = para.lower()
            # Score based on keyword overlap
            score = sum(1 for word in query_keywords if word in para_lower)
            # Boost score for longer, more informative paragraphs
            if len(para) > 50:
                score += 1
            scored_paragraphs.append((score, para))

        # Sort by score and take top paragraphs
        scored_paragraphs.sort(reverse=True)
        top_paragraphs = [p for s, p in scored_paragraphs[:3] if s > 0]

        # If no good matches, just take first few substantial paragraphs
        if not top_paragraphs and paragraphs:
            top_paragraphs = [p for p in paragraphs[:3] if len(p) > 30]

        if not top_paragraphs:
            top_paragraphs = paragraphs[:2] if paragraphs else ["No relevant information found."]

        # Build the answer
        answer = "\n\n".join(top_paragraphs)

        # Format as markdown bullet points if it looks like a list
        lines = answer.split("\n")
        if len(lines) > 3 and not answer.startswith("#"):
            # Try to structure it better
            formatted_lines = []
            for line in lines:
                line = line.strip()
                if line and not line.startswith("-") and not line.startswith("*"):
                    # Check if it looks like a list item
                    if line[0].isupper() and len(line) < 100:
                        formatted_lines.append(f"- {line}")
                    else:
                        formatted_lines.append(line)
                else:
                    formatted_lines.append(line)
            answer = "\n".join(formatted_lines)

        # Add warning about fallback mode
        answer += "\n\n⚠️ **Note:** Using simplified response mode. For intelligent, synthesized answers like ChatGPT, configure an AI model (Kimi, OpenAI, or better Ollama model)."

        return answer

    async def get_thread_history(self, thread_id: str, user_id: str) -> Optional[dict]:
        """Get full conversation history.

        Args:
            thread_id: Thread ID
            user_id: User ID (for authorization)

        Returns:
            Thread data with messages
        """
        thread = self.conversation_manager.get_thread(thread_id)
        if not thread or thread.user_id != user_id:
            return None

        return {
            "id": thread.id,
            "title": thread.title,
            "created_at": thread.created_at.isoformat(),
            "updated_at": thread.updated_at.isoformat(),
            "messages": [
                {
                    "role": msg.role.value,
                    "content": msg.content,
                    "citations": [c.to_dict() for c in msg.citations],
                    "created_at": msg.created_at.isoformat(),
                }
                for msg in thread.messages
            ],
        }

    async def delete_all_user_data(self, user_id: str) -> dict:
        """Delete all data for a user (conversations + documents).

        Args:
            user_id: User ID to delete

        Returns:
            Summary of deleted items
        """

        # Delete all conversations
        conversations = self.conversation_manager.list_conversations(user_id)
        deleted_conversations = 0
        for conv in conversations:
            if self.conversation_manager.delete_conversation(conv["id"], user_id):
                deleted_conversations += 1

        # Delete all documents from vector store
        deleted_chunks = await self.hybrid_searcher.delete_by_user(user_id)

        return {
            "conversations_deleted": deleted_conversations,
            "document_chunks_deleted": deleted_chunks,
            "user_id": user_id,
        }
