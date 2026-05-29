from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from chatwithdocs.ingestion.base import Chunk, ExtractionResult, Extractor, FileType

logger = logging.getLogger(__name__)


class PDFExtractor(Extractor):
    """Extract text and tables from PDF files using pdfplumber.

    This extractor handles:
    - Text extraction with page numbers
    - Table extraction (converted to markdown format)
    - Section detection (basic header detection)
    - Metadata extraction (title, author if available)
    """

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract content from PDF file.

        Args:
            file_path: Path to PDF file.

        Returns:
            ExtractionResult with chunks and metadata.
        """
        try:
            import pdfplumber
        except ImportError:
            error_msg = "pdfplumber not installed. Install with: uv pip install pdfplumber"
            logger.error(error_msg)
            return ExtractionResult(errors=[error_msg])

        chunks: list[Chunk] = []
        errors: list[str] = []
        metadata: dict[str, Any] = {}

        try:
            with pdfplumber.open(file_path) as pdf:
                # Extract document metadata
                if pdf.metadata:
                    metadata = {
                        "title": pdf.metadata.get("Title", ""),
                        "author": pdf.metadata.get("Author", ""),
                        "subject": pdf.metadata.get("Subject", ""),
                        "creator": pdf.metadata.get("Creator", ""),
                        "page_count": len(pdf.pages),
                    }

                # Extract content from each page
                for page_num, page in enumerate(pdf.pages, 1):
                    try:
                        # Extract text
                        text = page.extract_text()

                        if text and text.strip():
                            # Create chunks from page text
                            page_chunks = self._chunk_text(text, file_path, page_num)
                            chunks.extend(page_chunks)

                        # Extract tables
                        tables = page.extract_tables()
                        for table_idx, table in enumerate(tables):
                            if table:
                                table_chunk = self._table_to_chunk(
                                    table, file_path, page_num, table_idx
                                )
                                chunks.append(table_chunk)

                    except Exception as e:
                        error_msg = f"Error extracting page {page_num}: {e}"
                        logger.warning(error_msg)
                        errors.append(error_msg)

        except Exception as e:
            error_msg = f"Error opening PDF {file_path}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        return ExtractionResult(chunks=chunks, metadata=metadata, errors=errors)

    def _chunk_text(self, text: str, source_file: Path, page_num: int) -> list[Chunk]:
        """Split text into overlapping chunks.

        Args:
            text: Text content to chunk.
            source_file: Source file path.
            page_num: Page number.

        Returns:
            List of chunks.
        """
        chunks: list[Chunk] = []

        # Simple sentence-based chunking
        sentences = text.replace("\n", " ").split(". ")
        current_chunk = []
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
                        file_type=FileType.PDF,
                        page_number=page_num,
                        chunk_type="text",
                    )
                )

                # Keep overlap sentences for next chunk
                overlap_size = 0
                overlap_sentences = []
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
                    file_type=FileType.PDF,
                    page_number=page_num,
                    chunk_type="text",
                )
            )

        return chunks

    def _table_to_chunk(
        self, table: list[list[Any]], source_file: Path, page_num: int, table_idx: int
    ) -> Chunk:
        """Convert table to markdown format chunk.

        Args:
            table: Table data (list of rows).
            source_file: Source file path.
            page_num: Page number.
            table_idx: Table index.

        Returns:
            Chunk with table in markdown format.
        """
        # Convert table to markdown
        lines = []
        for i, row in enumerate(table):
            # Clean cell values
            cells = [str(cell).strip() if cell else "" for cell in row]
            lines.append("| " + " | ".join(cells) + " |")

            # Add separator after header row
            if i == 0:
                separators = ["---"] * len(cells)
                lines.append("| " + " | ".join(separators) + " |")

        table_text = "\n".join(lines)

        return Chunk(
            id=str(uuid.uuid4()),
            content=f"Table (Page {page_num}):\n{table_text}",
            source_file=source_file,
            file_type=FileType.PDF,
            page_number=page_num,
            chunk_type="table",
            metadata={"table_index": table_idx},
        )

    def supports(self, file_path: Path) -> bool:
        """Check if file is a PDF."""
        return file_path.suffix.lower() == ".pdf"

    @property
    def file_type(self) -> FileType:
        """Return PDF file type."""
        return FileType.PDF
