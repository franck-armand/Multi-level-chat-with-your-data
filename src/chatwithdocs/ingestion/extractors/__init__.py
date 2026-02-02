from __future__ import annotations

from chatwithdocs.ingestion.extractors.docx import DOCXExtractor
from chatwithdocs.ingestion.extractors.pdf import PDFExtractor
from chatwithdocs.ingestion.extractors.structured import StructuredExtractor
from chatwithdocs.ingestion.extractors.text import TextExtractor

__all__ = [
    "PDFExtractor",
    "DOCXExtractor",
    "StructuredExtractor",
    "TextExtractor",
]
