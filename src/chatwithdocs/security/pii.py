from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class PIIFinding:
    """A detected PII entity."""

    entity_type: str
    value: str
    start: int
    end: int
    confidence: float = 1.0


@dataclass
class PIIScanResult:
    """Result of PII scan."""

    has_pii: bool
    findings: List[PIIFinding]
    redacted_text: Optional[str] = None


class PIIDetector:
    """Detect and redact personally identifiable information.

    Uses regex-based patterns for common PII types.
    For production, consider using Presidio or similar libraries.
    """

    # PII detection patterns
    PATTERNS = {
        "EMAIL": (
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",
            0.95,
        ),
        "PHONE": (
            r"\b(?:\+?1[-.]?)?\(?[0-9]{3}\)?[-.]?[0-9]{3}[-.]?[0-9]{4}\b",
            0.9,
        ),
        "SSN": (
            r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b",
            0.95,
        ),
        "CREDIT_CARD": (
            r"\b(?:\d{4}[-.]?){3}\d{4}\b",
            0.9,
        ),
        "IP_ADDRESS": (
            r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b",
            0.85,
        ),
        "API_KEY": (
            r"\b(?:api[_-]?key|apikey|secret[_-]?key|token)[\s]*[=:]+[\s]*['\"]?[a-zA-Z0-9_\-]{16,}['\"]?",
            0.8,
        ),
    }

    def __init__(self, enabled: Optional[bool] = None):
        self.enabled = enabled if enabled is not None else settings.enable_pii_filter
        self._compiled_patterns = {
            name: (re.compile(pattern, re.IGNORECASE), confidence)
            for name, (pattern, confidence) in self.PATTERNS.items()
        }

    def scan(self, text: str) -> PIIScanResult:
        """Scan text for PII.

        Args:
            text: Text to scan

        Returns:
            PIIScanResult with findings
        """
        if not self.enabled or not text:
            return PIIScanResult(has_pii=False, findings=[])

        findings = []
        for entity_type, (pattern, confidence) in self._compiled_patterns.items():
            for match in pattern.finditer(text):
                findings.append(
                    PIIFinding(
                        entity_type=entity_type,
                        value=match.group(),
                        start=match.start(),
                        end=match.end(),
                        confidence=confidence,
                    )
                )

        has_pii = len(findings) > 0
        if has_pii:
            logger.info(f"Detected {len(findings)} PII entities in text")

        return PIIScanResult(has_pii=has_pii, findings=findings)

    def redact(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Redact PII from text.

        Args:
            text: Original text
            replacement: Replacement string

        Returns:
            Redacted text
        """
        if not self.enabled or not text:
            return text

        result = self.scan(text)
        if not result.has_pii:
            return text

        # Sort findings by position (reverse order to replace from end)
        sorted_findings = sorted(result.findings, key=lambda x: x.start, reverse=True)

        redacted = text
        for finding in sorted_findings:
            entity_replacement = f"[{finding.entity_type}]"
            redacted = redacted[: finding.start] + entity_replacement + redacted[finding.end :]

        logger.info(f"Redacted {len(result.findings)} PII entities")
        return redacted

    def redact_file_path(self, file_path: str) -> str:
        """Redact PII from a file path string.

        Args:
            file_path: File path that might contain PII

        Returns:
            Safe file path
        """
        # Sanitize path components that might contain usernames/emails
        parts = file_path.replace("\\", "/").split("/")
        safe_parts = []

        for part in parts:
            # Check if part looks like an email or PII
            if "@" in part or self.scan(part).has_pii:
                safe_parts.append("[USER]")
            else:
                safe_parts.append(part)

        return "/".join(safe_parts)


class PresidioPIIDetector(PIIDetector):
    """PII detector using Microsoft Presidio (if available).

    Falls back to regex-based detection if Presidio is not installed.
    """

    def __init__(self, enabled: Optional[bool] = None):
        super().__init__(enabled=enabled)
        self._analyzer = None
        self._anonymizer = None
        self._load_presidio()

    def _load_presidio(self):
        """Try to load Presidio if available."""
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_anonymizer import AnonymizerEngine

            self._analyzer = AnalyzerEngine()
            self._anonymizer = AnonymizerEngine()
            logger.info("Presidio loaded successfully")
        except ImportError:
            logger.debug("Presidio not available, using regex fallback")
            self._analyzer = None
            self._anonymizer = None

    def scan(self, text: str) -> PIIScanResult:
        """Scan using Presidio if available, otherwise fallback."""
        if not self.enabled or not text:
            return PIIScanResult(has_pii=False, findings=[])

        if self._analyzer is None:
            return super().scan(text)

        try:
            # Use Presidio analyzer
            results = self._analyzer.analyze(text=text, language="en")

            findings = []
            for result in results:
                findings.append(
                    PIIFinding(
                        entity_type=result.entity_type,
                        value=text[result.start : result.end],
                        start=result.start,
                        end=result.end,
                        confidence=result.score,
                    )
                )

            has_pii = len(findings) > 0
            return PIIScanResult(has_pii=has_pii, findings=findings)

        except Exception as e:
            logger.error(f"Presidio scan failed: {e}, falling back to regex")
            return super().scan(text)

    def redact(self, text: str, replacement: str = "[REDACTED]") -> str:
        """Redact using Presidio if available."""
        if not self.enabled or not text:
            return text

        if self._analyzer is None or self._anonymizer is None:
            return super().redact(text, replacement)

        try:
            from presidio_anonymizer.entities import (
                OperatorConfig,
            )

            # Analyze
            analyzer_results = self._analyzer.analyze(text=text, language="en")

            if not analyzer_results:
                return text

            # Anonymize
            anonymized = self._anonymizer.anonymize(
                text=text,
                analyzer_results=analyzer_results,
                operators={"DEFAULT": OperatorConfig("replace", {"new_value": replacement})},
            )

            return anonymized.text

        except Exception as e:
            logger.error(f"Presidio redaction failed: {e}, falling back to regex")
            return super().redact(text, replacement)


def get_pii_detector() -> PIIDetector:
    """Factory function to get the best available PII detector."""
    if settings.enable_pii_filter:
        # Try Presidio first, fall back to regex
        return PresidioPIIDetector()
    else:
        return PIIDetector(enabled=False)
