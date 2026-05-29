"""Confidence scoring for RAG responses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chatwithdocs.retrieval.hybrid_search import HybridSearchResult


@dataclass
class ConfidenceScore:
    """Confidence assessment of an answer."""

    score: float
    factors: dict[str, float]
    reasoning: str


class ConfidenceScorer:
    """Score confidence of RAG answers based on retrieval quality."""

    # Hedging language indicators (lower confidence)
    HEDGING_WORDS = {
        "might",
        "could",
        "may",
        "possibly",
        "perhaps",
        "seems",
        "appears",
        "likely",
        "uncertain",
        "unclear",
        "probably",
        "roughly",
        "approximately",
        "arguably",
    }

    # Strong language indicators (higher confidence)
    STRONG_WORDS = {"clearly", "definitely", "certainly", "definitely", "proven", "confirmed"}

    def score(
        self,
        query: str,
        retrieval_results: list[HybridSearchResult],
        response: str,
        intent: str | None = None,
    ) -> ConfidenceScore:
        """Score confidence of answer (0-1) based on multiple factors.

        Factors:
        - Retrieval quality: top result score, number of supporting results
        - Response certainty: presence of hedging/strong language
        - Query type: smalltalk vs document questions

        Args:
            query: User query
            retrieval_results: Retrieved documents
            response: Generated response
            intent: Query intent (smalltalk, document_question, etc)

        Returns:
            ConfidenceScore with overall score and breakdown
        """
        factors = {}

        # Factor 1: Retrieval quality (0-1)
        retrieval_factor = self._score_retrieval_quality(retrieval_results)
        factors["retrieval_quality"] = retrieval_factor

        # Factor 2: Result agreement (0-1)
        agreement_factor = self._score_result_agreement(retrieval_results)
        factors["result_agreement"] = agreement_factor

        # Factor 3: Response certainty (0-1)
        certainty_factor = self._score_response_certainty(response)
        factors["response_certainty"] = certainty_factor

        # Factor 4: Query type (adjustment)
        type_factor = self._score_query_type(intent)
        factors["query_type_factor"] = type_factor

        # Weighted average: retrieval (40%), agreement (30%), certainty (20%), type (10%)
        overall_score = (
            retrieval_factor * 0.40
            + agreement_factor * 0.30
            + certainty_factor * 0.20
            + type_factor * 0.10
        )

        # Clamp to 0-1
        overall_score = max(0.0, min(1.0, overall_score))

        reasoning = self._build_reasoning(factors, overall_score)

        return ConfidenceScore(score=overall_score, factors=factors, reasoning=reasoning)

    def _score_retrieval_quality(self, results: list[HybridSearchResult]) -> float:
        """Score based on top retrieval result quality.

        Returns:
            0.0 = no results
            0.3 = poor match (score < 0.5)
            0.6 = moderate match (score 0.5-0.7)
            0.85 = good match (score > 0.7)
        """
        if not results:
            return 0.0

        top_score = results[0].score

        if top_score < 0.5:
            return 0.3
        elif top_score < 0.65:
            return 0.6
        else:
            return 0.85

    def _score_result_agreement(self, results: list[HybridSearchResult]) -> float:
        """Score based on multiple supporting documents.

        More results with good scores = higher confidence in answer.

        Returns:
            0.3 = single result
            0.65 = 2+ results with moderate scores
            0.85 = 3+ results with good scores
        """
        if not results:
            return 0.0

        # Count results with score > 0.6
        good_results = sum(1 for r in results if r.score > 0.6)

        if good_results >= 3:
            return 0.85
        elif good_results >= 2:
            return 0.65
        else:
            return 0.3

    def _score_response_certainty(self, response: str) -> float:
        """Score based on language certainty in response.

        Hedging language = lower confidence
        Strong language = higher confidence

        Returns:
            0.5 = baseline (neutral response)
            0.3 = many hedging words
            0.7 = strong language
        """
        response_lower = response.lower()

        # Count hedging words
        hedging_count = sum(
            1 for word in self.HEDGING_WORDS if f" {word} " in f" {response_lower} "
        )

        # Count strong words
        strong_count = sum(1 for word in self.STRONG_WORDS if f" {word} " in f" {response_lower} ")

        # Score based on balance
        if hedging_count > 3:
            return 0.4
        elif strong_count > 2:
            return 0.75
        elif hedging_count > 0:
            return 0.55
        else:
            return 0.65

    def _score_query_type(self, intent: str | None) -> float:
        """Adjust confidence based on query type.

        Smalltalk = lower confidence needed
        Document questions = higher confidence needed

        Returns:
            1.0 = document question (higher bar for confidence)
            0.8 = mixed intent
            0.6 = smalltalk (lower bar)
        """
        if intent == "document_question":
            return 1.0
        elif intent == "mixed":
            return 0.8
        else:  # smalltalk
            return 0.6

    def _build_reasoning(self, factors: dict[str, float], overall_score: float) -> str:
        """Build human-readable reasoning for score."""
        score_band = (
            "high" if overall_score > 0.75 else "moderate" if overall_score > 0.5 else "low"
        )

        retrieval = factors.get("retrieval_quality", 0)
        agreement = factors.get("result_agreement", 0)
        certainty = factors.get("response_certainty", 0)

        parts = []
        if retrieval > 0.7:
            parts.append("strong retrieval match")
        elif retrieval < 0.4:
            parts.append("weak retrieval match")

        if agreement > 0.7:
            parts.append("multiple supporting sources")
        elif agreement < 0.4:
            parts.append("single source")

        if certainty > 0.7:
            parts.append("confident language")
        elif certainty < 0.5:
            parts.append("uncertain language")

        reasoning = f"{score_band.capitalize()} confidence: {', '.join(parts) if parts else 'neutral factors'}"
        return reasoning
