from __future__ import annotations

import logging
import re
from typing import List, Optional

from chatwithdocs.chat.models import Citation
from chatwithdocs.storage.vectors import ChunkMetadata

logger = logging.getLogger(__name__)


class CitationBuilder:
    """Build citations from retrieved chunks.

    Creates human-readable citations with source links and excerpts.
    """

    def __init__(
        self,
        max_excerpt_length: int = 200,
        citation_format: str = "superscript",  # "superscript", "footnote", "inline"
    ):
        self.max_excerpt_length = max_excerpt_length
        self.citation_format = citation_format

    def build_citation(
        self,
        chunk_id: str,
        content: str,
        metadata: ChunkMetadata,
        relevance_score: Optional[float] = None,
    ) -> Citation:
        """Build a citation from a retrieved chunk.

        Args:
            chunk_id: Unique chunk identifier
            content: Full chunk content
            metadata: Chunk metadata
            relevance_score: Optional relevance score

        Returns:
            Citation object
        """
        excerpt = self._generate_excerpt(content)

        return Citation(
            source_file=metadata.source_file,
            excerpt=excerpt,
            page_number=metadata.page_number,
            section=metadata.section_header,
            chunk_id=chunk_id,
            relevance_score=relevance_score,
        )

    def build_citations(
        self,
        results: List[tuple[str, str, ChunkMetadata, Optional[float]]],
    ) -> List[Citation]:
        """Build multiple citations from search results.

        Args:
            results: List of (chunk_id, content, metadata, score) tuples

        Returns:
            List of citations
        """
        citations = []
        for chunk_id, content, metadata, score in results:
            try:
                citation = self.build_citation(chunk_id, content, metadata, score)
                citations.append(citation)
            except Exception as e:
                logger.error(f"Failed to build citation for {chunk_id}: {e}")

        return citations

    def _generate_excerpt(self, content: str) -> str:
        """Generate a concise excerpt from content.

        Args:
            content: Full content

        Returns:
            Truncated excerpt
        """
        # Clean up whitespace
        content = re.sub(r"\s+", " ", content.strip())

        if len(content) <= self.max_excerpt_length:
            return content

        # Try to break at a sentence boundary
        truncated = content[: self.max_excerpt_length]

        # Look for sentence ending
        last_period = truncated.rfind(". ")
        if last_period > self.max_excerpt_length * 0.5:
            return truncated[: last_period + 1]

        # Otherwise break at word boundary
        last_space = truncated.rfind(" ")
        if last_space > 0:
            return truncated[:last_space] + "..."

        return truncated + "..."

    def format_citations(
        self,
        citations: List[Citation],
        format_type: Optional[str] = None,
    ) -> str:
        """Format citations for display.

        Args:
            citations: List of citations
            format_type: Format type (defaults to self.citation_format)

        Returns:
            Formatted citation string
        """
        fmt = format_type or self.citation_format

        if not citations:
            return ""

        if fmt == "superscript":
            return self._format_superscript(citations)
        elif fmt == "footnote":
            return self._format_footnote(citations)
        elif fmt == "inline":
            return self._format_inline(citations)
        else:
            return self._format_superscript(citations)

    def _format_superscript(self, citations: List[Citation]) -> str:
        """Format as superscript numbers (e.g., [¹][²])."""
        refs = []
        for i, cit in enumerate(citations, 1):
            ref = self._format_source_ref(cit)
            refs.append(f"[{i}] {ref}")
        return "\n".join(refs)

    def _format_footnote(self, citations: List[Citation]) -> str:
        """Format as footnotes."""
        refs = ["Sources:"]
        for i, cit in enumerate(citations, 1):
            ref = self._format_source_ref(cit)
            refs.append(f"  {i}. {ref}")
        return "\n".join(refs)

    def _format_inline(self, citations: List[Citation]) -> str:
        """Format inline with source info."""
        refs = []
        for cit in citations:
            ref = self._format_source_ref(cit)
            refs.append(f"[{ref}]")
        return " ".join(refs)

    def _format_source_ref(self, citation: Citation) -> str:
        """Format a single source reference.

        Example: "document.pdf, Page 5, Section: Introduction"
        """
        parts = [citation.source_file]

        if citation.page_number:
            parts.append(f"Page {citation.page_number}")

        if citation.section:
            parts.append(f"Section: {citation.section}")

        return ", ".join(parts)

    def create_link(self, citation: Citation) -> Optional[str]:
        """Create a clickable link to the source (if applicable).

        Args:
            citation: Citation object

        Returns:
            Link URL or None
        """
        # For local files, we could create a file:// link
        # For now, return None as we don't have a viewer
        return None


class MergedCitationBuilder(CitationBuilder):
    """Citation builder that merges citations from the same source."""

    def build_citations(
        self,
        results: List[tuple[str, str, ChunkMetadata, Optional[float]]],
    ) -> List[Citation]:
        """Build citations, merging duplicates from same source/page."""
        citations = super().build_citations(results)

        # Group by source file and page
        grouped: dict = {}
        for cit in citations:
            key = (cit.source_file, cit.page_number)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(cit)

        # Merge groups
        merged = []
        for (source, page), group in grouped.items():
            if len(group) == 1:
                merged.append(group[0])
            else:
                # Merge excerpts
                combined_excerpt = " ".join(c.excerpt for c in group)
                combined_excerpt = self._generate_excerpt(combined_excerpt)

                # Use highest relevance score
                scores = [c.relevance_score for c in group if c.relevance_score]
                best_score = max(scores) if scores else None

                merged.append(
                    Citation(
                        source_file=source,
                        excerpt=combined_excerpt,
                        page_number=page,
                        section=group[0].section,
                        chunk_id=group[0].chunk_id,
                        relevance_score=best_score,
                    )
                )

        # Sort by relevance
        merged.sort(key=lambda x: x.relevance_score or 0, reverse=True)

        return merged
