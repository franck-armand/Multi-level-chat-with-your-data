from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from chatwithdocs.ingestion.base import Chunk, ExtractionResult, Extractor, FileType
from chatwithdocs.ingestion.extractors.pdf import PDFExtractor

logger = logging.getLogger(__name__)


class MarkerPDFExtractor(Extractor):
    """Extract text and tables from PDF files using marker-pdf.

    This extractor handles:
    - Layout-aware text extraction
    - Table extraction (markdown format)
    - OCR for scanned PDFs (smart mode)
    - Semantic chunking by blocks (titles, paragraphs, tables)
    - Metadata preservation (page numbers, sections)
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        force_ocr: bool = False,
        use_fallback: bool = True,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.force_ocr = force_ocr
        self.use_fallback = use_fallback
        self._fallback_extractor = PDFExtractor(chunk_size, chunk_overlap)

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract content from PDF file using marker-pdf.

        Args:
            file_path: Path to PDF file.

        Returns:
            ExtractionResult with chunks and metadata.
        """
        try:
            from marker.converters.pdf import PdfConverter
            from marker.models import create_model_dict
        except ImportError:
            logger.warning(
                "marker-pdf not installed. Install with: uv pip install marker-pdf"
            )
            return self._fallback_extractor.extract(file_path)

        chunks: list[Chunk] = []
        errors: list[str] = []
        metadata: dict[str, Any] = {}

        try:
            model_dict = create_model_dict()
            converter = PdfConverter(artifact_dict=model_dict)

            import os

            os.environ["OCR_ALL_PAGES"] = "false" if not self.force_ocr else "true"

            rendered = converter(file_path)
            blocks = rendered.blocks

            if not blocks or len(blocks) == 0:
                logger.warning(f"No content extracted from {file_path}")
                if self.use_fallback:
                    return self._fallback_extractor.extract(file_path)
                return ExtractionResult(chunks=[], metadata={}, errors=["No content extracted"])

            for block in blocks:
                block_type = block.type.lower() if hasattr(block, "type") else "text"
                page_num = getattr(block, "page_num", 1) or 1

                content = self._extract_block_content(block)
                if not content or not content.strip():
                    continue

                if block_type == "table":
                    chunk = Chunk(
                        id=str(uuid.uuid4()),
                        content=content,
                        source_file=file_path,
                        file_type=FileType.PDF,
                        page_number=page_num,
                        chunk_type="table",
                        section_header=self._extract_section_header(block),
                        metadata={"layout": "table"},
                    )
                    chunks.append(chunk)
                elif block_type == "title":
                    chunk = Chunk(
                        id=str(uuid.uuid4()),
                        content=content,
                        source_file=file_path,
                        file_type=FileType.PDF,
                        page_number=page_num,
                        chunk_type="title",
                        section_header=content,
                    )
                    chunks.append(chunk)
                elif block_type in ("text", "caption", "formula", "code"):
                    text_chunks = self._chunk_text(
                        content, file_path, page_num, block_type
                    )
                    chunks.extend(text_chunks)
                else:
                    text_chunks = self._chunk_text(
                        content, file_path, page_num, "text"
                    )
                    chunks.extend(text_chunks)

            metadata = {
                "page_count": max(
                    (getattr(block, "page_num", 1) or 1) for block in blocks
                )
                if blocks
                else 0,
                "extractor": "marker-pdf",
            }

            for block in blocks[:1]:
                if hasattr(block, "bbox"):
                    metadata["has_layout"] = True
                    break

        except Exception as e:
            error_msg = f"Marker extraction failed: {e}"
            logger.warning(error_msg)
            errors.append(error_msg)

            if self.use_fallback:
                logger.info("Falling back to pdfplumber")
                return self._fallback_extractor.extract(file_path)

            return ExtractionResult(chunks=[], metadata=metadata, errors=errors)

        return ExtractionResult(chunks=chunks, metadata=metadata, errors=errors)

    def _extract_block_content(self, block: Any) -> str:
        """Extract text content from a marker block.

        Args:
            block: Marker block object.

        Returns:
            Text content as string.
        """
        if hasattr(block, "text"):
            return str(block.text)
        elif hasattr(block, "content"):
            return str(block.content)
        elif hasattr(block, "markdown"):
            return str(block.markdown)
        return ""

    def _extract_section_header(self, block: Any) -> str | None:
        """Extract section header from a block if available.

        Args:
            block: Marker block object.

        Returns:
            Section header or None.
        """
        if hasattr(block, "section_title"):
            return block.section_title
        elif hasattr(block, "parent_heading"):
            return block.parent_heading
        return None

    def _chunk_text(
        self, text: str, source_file: Path, page_num: int, block_type: str = "text"
    ) -> list[Chunk]:
        """Split text into overlapping chunks.

        Args:
            text: Text content to chunk.
            source_file: Source file path.
            page_num: Page number.
            block_type: Type of block (text, title, caption, etc.).

        Returns:
            List of chunks.
        """
        if not text or len(text) <= self.chunk_size:
            return [
                Chunk(
                    id=str(uuid.uuid4()),
                    content=text,
                    source_file=source_file,
                    file_type=FileType.PDF,
                    page_number=page_num,
                    chunk_type=block_type,
                )
            ]

        chunks: list[Chunk] = []
        current_pos = 0
        text_len = len(text)

        while current_pos < text_len:
            end_pos = min(current_pos + self.chunk_size, text_len)

            if end_pos < text_len:
                cut_point = text.rfind("\n", current_pos, end_pos)
                if cut_point == -1 or cut_point < current_pos:
                    cut_point = end_pos
                else:
                    cut_point = cut_point + 1
            else:
                cut_point = end_pos

            chunk_text = text[current_pos:cut_point].strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        id=str(uuid.uuid4()),
                        content=chunk_text,
                        source_file=source_file,
                        file_type=FileType.PDF,
                        page_number=page_num,
                        chunk_type=block_type,
                    )
                )

            current_pos = cut_point

            if current_pos < self.chunk_overlap or cut_point == end_pos:
                break

            current_pos = max(current_pos - self.chunk_overlap, current_pos)

        return chunks

    def supports(self, file_path: Path) -> bool:
        """Check if file is a PDF."""
        return file_path.suffix.lower() == ".pdf"

    @property
    def file_type(self) -> FileType:
        """Return PDF file type."""
        return FileType.PDF