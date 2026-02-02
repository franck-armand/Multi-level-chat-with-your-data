from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class InjectionCheck:
    """Result of prompt injection detection."""

    is_safe: bool
    reason: Optional[str] = None
    confidence: float = 0.0  # 0.0 to 1.0
    patterns_matched: List[str] = None

    def __post_init__(self):
        if self.patterns_matched is None:
            self.patterns_matched = []


class PromptInjectionDetector:
    """Detects and prevents prompt injection attacks.

    Uses a multi-layered approach:
    1. Heuristic pattern matching (fast)
    2. Keyword/signature detection
    3. Structure analysis
    """

    # High-confidence injection patterns
    HIGH_RISK_PATTERNS = [
        # Attempts to override system instructions
        r"ignore\s+(?:your\s+)?(?:previous\s+)?instructions",
        r"ignore\s+(?:your\s+)?(?:system\s+)?prompt",
        r"disregard\s+(?:your\s+)?(?:previous\s+)?instructions",
        r"forget\s+(?:your\s+)?(?:previous\s+)?instructions",
        # Role manipulation attempts
        r"you\s+are\s+now\s+(?:a\s+)?",
        r"act\s+as\s+(?:if\s+)?you\s+(?:are\s+)?",
        r"pretend\s+(?:to\s+)?be\s+(?:a\s+)?",
        r"from\s+now\s+on\s+you\s+are",
        # System prompt extraction attempts
        r"repeat\s+(?:the\s+)?(?:words\s+)?above",
        r"repeat\s+(?:the\s+)?(?:words\s+)?before",
        r"show\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?prompt",
        r"print\s+(?:your\s+)?(?:system\s+)?prompt",
        r"what\s+(?:were\s+)?(?:your\s+)?instructions",
        # Delimiter-based attacks
        r"```\s*system",
        r"```\s*instructions",
        r"<\s*system\s*>",
        r"<\s*instructions\s*>",
        # API key / credential extraction - direct value patterns
        r"\b(?:api[_-]?key|apikey|secret[_-]?key|token)[\s]*[=:]+[\s]*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?",
        # API key / credential extraction - extraction request patterns
        r"(?:show|give|send|tell)\s+(?:me\s+)?(?:your\s+)?(?:api[_-]?\s*key|secret[_-]?\s*key|token|password)",
        r"(?:what\s+is|reveal|expose|disclose|share)\s+(?:your\s+)?(?:api[_-]?\s*key|secret[_-]?\s*key|token|password)",
    ]

    # Medium-risk patterns requiring additional context
    MEDIUM_RISK_PATTERNS = [
        # SQL injection-like patterns
        r";\s*DROP\s+TABLE",
        r";\s*DELETE\s+FROM",
        r"UNION\s+SELECT",
        # Suspicious delimiters or escape sequences
        r"\\\\n\\s*system",
        r"\\\\n\\s*assistant",
        r"\\\\n\\s*user",
        # Attempts to create new instructions
        r"new\s+instructions?:",
        r"updated\s+instructions?:",
        r"override\s+(?:with\s+)?:",
    ]

    # Suspicious keywords that raise lower confidence alerts
    SUSPICIOUS_KEYWORDS = [
        "jailbreak",
        "prompt injection",
        "system prompt",
        "ignore rules",
        "bypass",
        "hack",
        "exploit",
    ]

    def __init__(self, enabled: Optional[bool] = None):
        self.enabled = enabled if enabled is not None else settings.enable_injection_detection
        self._high_risk_regex = [re.compile(p, re.IGNORECASE) for p in self.HIGH_RISK_PATTERNS]
        self._medium_risk_regex = [re.compile(p, re.IGNORECASE) for p in self.MEDIUM_RISK_PATTERNS]

    def check(self, prompt: str) -> InjectionCheck:
        """Check a prompt for injection attempts.

        Args:
            prompt: User prompt to check

        Returns:
            InjectionCheck result
        """
        if not self.enabled:
            return InjectionCheck(is_safe=True, reason="Detection disabled")

        if not prompt or not isinstance(prompt, str):
            return InjectionCheck(is_safe=True, reason="Empty or invalid prompt")

        # Check high-risk patterns
        high_risk_matches = []
        for pattern in self._high_risk_regex:
            if pattern.search(prompt):
                high_risk_matches.append(pattern.pattern[:50] + "...")

        if high_risk_matches:
            logger.warning(f"High-risk injection patterns detected: {high_risk_matches}")
            return InjectionCheck(
                is_safe=False,
                reason="High-risk injection patterns detected",
                confidence=0.9,
                patterns_matched=high_risk_matches,
            )

        # Check medium-risk patterns
        medium_risk_matches = []
        for pattern in self._medium_risk_regex:
            if pattern.search(prompt):
                medium_risk_matches.append(pattern.pattern[:50] + "...")

        if medium_risk_matches:
            # For medium risk, check if there are multiple indicators
            suspicious_count = sum(
                1 for keyword in self.SUSPICIOUS_KEYWORDS if keyword.lower() in prompt.lower()
            )

            if suspicious_count >= 2 or len(medium_risk_matches) >= 2:
                logger.warning("Multiple medium-risk indicators detected")
                return InjectionCheck(
                    is_safe=False,
                    reason="Multiple suspicious patterns detected",
                    confidence=0.75,
                    patterns_matched=medium_risk_matches,
                )

        # Check for suspicious keywords (low confidence)
        keyword_matches = [
            keyword for keyword in self.SUSPICIOUS_KEYWORDS if keyword.lower() in prompt.lower()
        ]

        if keyword_matches:
            logger.info(f"Suspicious keywords found (low confidence): {keyword_matches}")
            return InjectionCheck(
                is_safe=True,  # Still allow but with low confidence
                reason=f"Suspicious keywords detected: {', '.join(keyword_matches)}",
                confidence=0.3,
                patterns_matched=keyword_matches,
            )

        return InjectionCheck(is_safe=True, reason="No injection patterns detected", confidence=1.0)

    def sanitize(self, prompt: str) -> str:
        """Attempt to sanitize a potentially malicious prompt.

        Note: This is a best-effort approach. When in doubt, reject.

        Args:
            prompt: Potentially malicious prompt

        Returns:
            Sanitized prompt (may still be unsafe)
        """
        # Remove common injection delimiters
        sanitized = prompt

        # Remove system instruction markers
        sanitized = re.sub(r"```\s*system.*?```", "", sanitized, flags=re.DOTALL | re.IGNORECASE)
        sanitized = re.sub(
            r"<\s*system\s*>.*?</\s*system\s*>", "", sanitized, flags=re.DOTALL | re.IGNORECASE
        )

        # Normalize whitespace
        sanitized = re.sub(r"\s+", " ", sanitized)

        return sanitized.strip()

    def get_safe_alternative(self, prompt: str, reason: str) -> str:
        """Generate a safe alternative message when prompt is blocked.

        Args:
            prompt: Original blocked prompt
            reason: Reason for blocking

        Returns:
            Safe alternative suggestion
        """
        return (
            f"Your message appears to contain content that violates our safety guidelines "
            f"({reason}). Please rephrase your question without using system commands, "
            f"instruction overrides, or attempts to access internal configurations. "
            f"I'm here to help with questions about your uploaded documents!"
        )


class ContentFilter:
    """Additional content filtering for safety."""

    # Toxic/offensive patterns
    TOXIC_PATTERNS = [
        r"\b(hate|kill|die|violence|attack)\b",
    ]

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._toxic_regex = [re.compile(p, re.IGNORECASE) for p in self.TOXIC_PATTERNS]

    def check_content(self, text: str) -> InjectionCheck:
        """Check content for toxic/offensive material."""
        if not self.enabled:
            return InjectionCheck(is_safe=True)

        matches = []
        for pattern in self._toxic_regex:
            if pattern.search(text):
                matches.append(pattern.pattern)

        if matches:
            return InjectionCheck(
                is_safe=False,
                reason="Potentially harmful content detected",
                confidence=0.6,
                patterns_matched=matches,
            )

        return InjectionCheck(is_safe=True, confidence=1.0)
