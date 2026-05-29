"""Query validation and sanitization."""

from __future__ import annotations


class QueryValidator:
    """Validate user queries before processing."""

    # Suspicious patterns that might indicate injection attempts
    SUSPICIOUS_PATTERNS = {
        "curl ",
        "exec(",
        "bash",
        "sh -c",
        "sql ",
        "drop table",
        "delete from",
        "<script",
        "javascript:",
        "${",
        "{{",
        "ignore previous",
        "forget previous",
        "system prompt",
        "jailbreak",
    }

    def validate(self, query: str) -> tuple[bool, str | None]:
        """Validate query and return (is_valid, error_message).

        Args:
            query: User query to validate

        Returns:
            Tuple of (is_valid, error_message).
            If valid: (True, None)
            If invalid: (False, error_message)
        """
        # Check length
        if not query or len(query.strip()) == 0:
            return False, "Query cannot be empty"

        if len(query) < 3:
            return False, "Query must be at least 3 characters"

        if len(query) > 5000:
            return False, "Query must be less than 5000 characters"

        # Check for suspicious patterns (case-insensitive)
        query_lower = query.lower()
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern in query_lower:
                return False, f"Query contains suspicious pattern: '{pattern}'"

        # Check for excessive special characters (potential injection)
        special_chars = sum(1 for c in query if c in '{}[]<>\\"|\'~`')
        if special_chars > 20:
            return False, "Query contains too many special characters"

        # Check for null bytes
        if "\x00" in query:
            return False, "Query contains invalid characters"

        return True, None
