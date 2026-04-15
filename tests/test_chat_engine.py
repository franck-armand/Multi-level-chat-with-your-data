from __future__ import annotations

import asyncio

from chatwithdocs.chat.engine import ChatEngine
from chatwithdocs.chat.models import Thread


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

        assert "Bonjour! Hello!" in response
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

        assert "Bonjour! Hello!" in response
        assert "document part of your message" in response

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
