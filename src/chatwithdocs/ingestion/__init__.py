from __future__ import annotations

from chatwithdocs.ingestion.base import Chunk, ExtractionResult, Extractor, FileType
from chatwithdocs.ingestion.extractors.docx import DOCXExtractor
from chatwithdocs.ingestion.extractors.pdf import PDFExtractor
from chatwithdocs.ingestion.extractors.structured import StructuredExtractor
from chatwithdocs.ingestion.extractors.text import TextExtractor
from chatwithdocs.ingestion.pipeline import IngestionPipeline

__all__ = [
    "Chunk",
    "ExtractionResult",
    "Extractor",
    "FileType",
    "PDFExtractor",
    "DOCXExtractor",
    "StructuredExtractor",
    "TextExtractor",
    "IngestionPipeline",
]
