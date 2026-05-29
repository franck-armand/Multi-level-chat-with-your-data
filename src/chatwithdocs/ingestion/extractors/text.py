from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from chatwithdocs.ingestion.base import Chunk, ExtractionResult, Extractor, FileType

logger = logging.getLogger(__name__)


class TextExtractor(Extractor):
    """Extract text from plain text and markdown files.

    This extractor handles:
    - Plain text files (.txt)
    - Markdown files (.md, .markdown)
    - Header boundary detection for markdown (lines starting with #)
    - Sentence-based chunking with overlap
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract content from text or markdown file.

        Args:
            file_path: Path to text or markdown file.

        Returns:
            ExtractionResult with chunks and metadata.
        """
        chunks: list[Chunk] = []
        errors: list[str] = []
        metadata: dict[str, Any] = {}

        try:
            # Read file content
            try:
                content = file_path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                # Try with different encoding
                content = file_path.read_text(encoding="latin-1")

            if not content.strip():
                logger.warning(f"Empty file: {file_path}")
                return ExtractionResult(
                    metadata={"file_size": 0, "line_count": 0},
                    errors=["File is empty"],
                )

            # Determine file type
            suffix = file_path.suffix.lower()
            if suffix == ".md" or suffix == ".markdown":
                file_type = FileType.MARKDOWN
                is_markdown = True
            else:
                file_type = FileType.TXT
                is_markdown = False

            # Basic metadata
            lines = content.splitlines()
            metadata = {
                "file_size": len(content),
                "line_count": len(lines),
                "file_type": suffix,
            }

            # For markdown, try to respect header boundaries
            if is_markdown:
                chunks = self._extract_markdown(content, file_path, lines)
            else:
                # Plain text - chunk by sentences
                chunks = self._chunk_text(content, file_path, file_type, None)

        except Exception as e:
            error_msg = f"Error reading text file {file_path}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        return ExtractionResult(chunks=chunks, metadata=metadata, errors=errors)

    def _extract_markdown(self, content: str, source_file: Path, lines: list[str]) -> list[Chunk]:
        """Extract chunks from markdown content, respecting header boundaries.

        Args:
            content: Full file content.
            source_file: Source file path.
            lines: List of lines in the file.

        Returns:
            List of chunks.
        """
        chunks: list[Chunk] = []

        # Parse sections based on headers
        sections: list[tuple[str | None, list[str]]] = []
        current_header: str | None = None
        current_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # Check if this is a header line
            if stripped.startswith("#"):
                # Save previous section if it has content
                if current_lines:
                    sections.append((current_header, current_lines))
                    current_lines = []
                # Update header (remove # characters and whitespace)
                current_header = stripped.lstrip("#").strip()
            else:
                current_lines.append(line)

        # Don't forget the last section
        if current_lines:
            sections.append((current_header, current_lines))

        # If no headers found, treat as single section
        if not sections:
            sections = [(None, lines)]

        # Create chunks from each section
        for section_header, section_lines in sections:
            section_text = "\n".join(section_lines).strip()
            if not section_text:
                continue

            section_chunks = self._chunk_text(
                section_text, source_file, FileType.MARKDOWN, section_header
            )
            chunks.extend(section_chunks)

        return chunks

    def _chunk_text(
        self, text: str, source_file: Path, file_type: FileType, section_header: str | None
    ) -> list[Chunk]:
        """Split text into overlapping chunks using sentence-based chunking.

        Args:
            text: Text content to chunk.
            source_file: Source file path.
            file_type: Type of file (TXT or MARKDOWN).
            section_header: Current section header (for markdown).

        Returns:
            List of chunks.
        """
        chunks: list[Chunk] = []

        # Replace newlines with spaces for sentence splitting
        sentences = text.replace("\n", " ").split(". ")
        current_chunk: list[str] = []
        current_size = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # Add period back if it was removed
            if not sentence.endswith("."):
                sentence += "."

            sentence_size = len(sentence)

            # If adding this sentence would exceed chunk size, save current chunk
            if current_size + sentence_size > self.chunk_size and current_chunk:
                chunk_text = " ".join(current_chunk)
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        content=chunk_text,
                        source_file=source_file,
                        file_type=file_type,
                        section_header=section_header,
                        chunk_type="text",
                    )
                )

                # Keep overlap sentences for next chunk
                overlap_size = 0
                overlap_sentences: list[str] = []
                for s in reversed(current_chunk):
                    if overlap_size + len(s) > self.chunk_overlap:
                        break
                    overlap_sentences.insert(0, s)
                    overlap_size += len(s)

                current_chunk = overlap_sentences
                current_size = overlap_size

            current_chunk.append(sentence)
            current_size += sentence_size

        # Don't forget the last chunk
        if current_chunk:
            chunk_text = " ".join(current_chunk)
            chunks.append(
                Chunk(
                    id=str(uuid.uuid4()),
                    content=chunk_text,
                    source_file=source_file,
                    file_type=file_type,
                    section_header=section_header,
                    chunk_type="text",
                )
            )

        return chunks

    def supports(self, file_path: Path) -> bool:
        """Check if file is a supported text format.

        Args:
            file_path: Path to check.

        Returns:
            True if this extractor can handle the file, False otherwise.
        """
        suffix = file_path.suffix.lower()
        return suffix in [".txt", ".md", ".markdown"]

    @property
    def file_type(self) -> FileType:
        """Return the file type this extractor handles.

        Returns:
            TXT as the primary file type (dynamic based on actual file).
        """
        return FileType.TXT
