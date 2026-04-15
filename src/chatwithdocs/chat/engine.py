from __future__ import annotations

import logging
import re
import unicodedata
from typing import List, Optional

from chatwithdocs.chat.manager import ConversationManager
from chatwithdocs.chat.models import Citation, MessageRole, Thread
from chatwithdocs.config import settings
from chatwithdocs.embedding import EmbeddingRouter
from chatwithdocs.llm.client import LLMMessage, LLMRouter
from chatwithdocs.retrieval import HybridSearcher, get_reranker
from chatwithdocs.retrieval.citation import CitationBuilder
from chatwithdocs.retrieval.hybrid_search import HybridSearchResult
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
    "thanks",
    "thank you",
    "bonjour",
    "salut",
    "bonsoir",
    "coucou",
    "ca va",
    "comment ca va",
    "merci",
    "merci beaucoup",
    "yo",
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
        # Get or create thread
        if thread_id:
            thread = self.conversation_manager.get_thread(thread_id)
            if not thread or thread.user_id != user_id:
                thread = self.conversation_manager.create_thread(user_id)
        else:
            thread = self.conversation_manager.create_thread(user_id)

        # Add user message
        self.conversation_manager.add_user_message(thread.id, message)

        intent = await self._resolve_query_intent(message)
        search_results = []
        if intent != "smalltalk":
            # Retrieve context (filtered by user_id)
            search_results = await self._retrieve_context(message, user_id)

        # Rerank if enabled
        if settings.rerank_results and search_results:
            from chatwithdocs.retrieval.reranker import RerankedResult

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
        )

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
        if intent == "smalltalk":
            return self._build_smalltalk_response()

        if not search_results:
            if intent == "mixed":
                return (
                    f"{self._build_smalltalk_response()} "
                    "I couldn't find supporting information for the document part of your message in the files you uploaded yet. "
                    "Please mention the document/topic you want me to inspect, or upload the relevant file."
                )
            return (
                "I couldn't find supporting information for that in your uploaded documents. "
                "Please rephrase the question, mention the document/topic you want, or upload relevant files."
            )

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
            answer = f"{self._build_smalltalk_response()} {answer}"

        return answer.strip()

    def _classify_query_intent(self, query: str) -> str:
        """Classify the query as smalltalk, document question, mixed, or ambiguous."""
        normalized = self._normalize_text(query)
        if not normalized:
            return "document_question"

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

    def _build_smalltalk_response(self) -> str:
        """Return a friendly conversational opener."""
        return (
            "Bonjour! Hello! I'm here to help with questions about your uploaded documents. "
            "Ask about a file, a topic inside it, or upload documents if you want grounded answers."
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
