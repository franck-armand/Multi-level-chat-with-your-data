from __future__ import annotations

import asyncio

from chatwithdocs.chat.engine import AnswerabilityDecision, ChatEngine
from chatwithdocs.chat.models import Thread
from chatwithdocs.retrieval.hybrid_search import HybridSearchResult
from chatwithdocs.storage.vectors import ChunkMetadata


class TestChatEngineResponseGuards:
    def test_smalltalk_does_not_claim_document_support(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "hello",
                [],
                [],
                thread,
                intent=engine._classify_query_intent("hello"),
            )
        )

        assert "uploaded documents" in response
        assert "couldn't find relevant information" not in response.lower()

    def test_french_smalltalk_is_detected(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response("Bonjour", [], [], thread, intent=engine._classify_query_intent("Bonjour"))
        )

        assert "Bonjour !" in response
        assert "supporting information" not in response

    def test_french_accented_smalltalk_is_normalized(self):
        engine = ChatEngine.__new__(ChatEngine)

        intent = engine._classify_query_intent("Ça va ?")

        assert intent == "smalltalk"

    def test_mixed_smalltalk_and_document_question_is_detected(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "Bonjour, peux-tu resumer le contrat ?",
                [],
                [],
                thread,
                intent=engine._classify_query_intent("Bonjour, peux-tu resumer le contrat ?"),
            )
        )

        assert "Bonjour !" in response
        assert "partie documentaire" in response

    def test_empty_retrieval_uses_grounded_fallback(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "What does the contract say?",
                [],
                [],
                thread,
                intent=engine._classify_query_intent("What does the contract say?"),
            )
        )

        assert "uploaded documents" in response
        assert "supporting information" in response

    def test_ambiguous_query_can_be_routed_by_model_to_smalltalk(self):
        engine = ChatEngine.__new__(ChatEngine)

        async def fake_model_classifier(query: str) -> str:
            assert query == "sup"
            return "smalltalk"

        engine._classify_query_intent_with_model = fake_model_classifier

        intent = asyncio.run(engine._resolve_query_intent("sup"))

        assert intent == "smalltalk"

    def test_ambiguous_query_falls_back_to_document_question_on_invalid_model_output(self):
        engine = ChatEngine.__new__(ChatEngine)

        async def fake_model_classifier(query: str) -> str | None:
            assert query == "hmm"
            return None

        engine._classify_query_intent_with_model = fake_model_classifier

        intent = asyncio.run(engine._resolve_query_intent("hmm"))

        assert intent == "document_question"

    def test_answerability_marks_vague_query_for_clarification(self):
        engine = ChatEngine.__new__(ChatEngine)

        decision = engine._assess_answerability("What about this one?", [], "document_question")

        assert decision.status == "needs_clarification"
        assert decision.reason == "underspecified_query"

    def test_answerability_marks_very_weak_retrieval_as_not_grounded(self):
        engine = ChatEngine.__new__(ChatEngine)
        results = [
            HybridSearchResult(
                id="chunk-1",
                content="thin evidence",
                score=0.01,
                metadata=ChunkMetadata(source_file="doc.txt", file_type="txt", user_id="user1"),
            )
        ]

        decision = engine._assess_answerability("What does the contract say?", results, "document_question")

        assert decision.status == "not_grounded"
        assert decision.reason == "very_low_retrieval_score"

    def test_answerability_allows_strong_retrieval(self):
        engine = ChatEngine.__new__(ChatEngine)
        results = [
            HybridSearchResult(
                id="chunk-1",
                content="The contract allows termination with 30 days notice.",
                score=0.08,
                metadata=ChunkMetadata(source_file="contract.txt", file_type="txt", user_id="user1"),
            ),
            HybridSearchResult(
                id="chunk-2",
                content="Termination requires written notice.",
                score=0.06,
                metadata=ChunkMetadata(source_file="contract.txt", file_type="txt", user_id="user1"),
            ),
        ]

        decision = engine._assess_answerability("What does the contract say?", results, "document_question")

        assert decision.status == "answerable"

    def test_generate_response_uses_clarification_gate(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "What about this one?",
                [],
                [],
                thread,
                intent="document_question",
                answerability=AnswerabilityDecision(
                    status="needs_clarification",
                    reason="underspecified_query",
                    confidence=0.9,
                ),
            )
        )

        assert "need a bit more context" in response

    def test_generate_response_uses_french_clarification_gate(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "Et ce document ?",
                [],
                [],
                thread,
                intent="document_question",
                answerability=AnswerabilityDecision(
                    status="needs_clarification",
                    reason="underspecified_query",
                    confidence=0.9,
                ),
            )
        )

        assert "J'ai besoin d'un peu plus de contexte" in response

    def test_generate_response_uses_french_not_grounded_message(self):
        engine = ChatEngine.__new__(ChatEngine)
        thread = Thread(user_id="user1")

        response = asyncio.run(
            engine._generate_response(
                "Que dit le contrat ?",
                [],
                [],
                thread,
                intent="document_question",
                answerability=AnswerabilityDecision(
                    status="not_grounded",
                    reason="very_low_retrieval_score",
                    confidence=0.95,
                ),
            )
        )

        assert "Je n'ai pas assez d'elements fiables" in response
