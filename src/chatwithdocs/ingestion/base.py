from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any


class FileType(Enum):
    PDF = auto()
    DOCX = auto()
    CSV = auto()
    EXCEL = auto()
    TXT = auto()
    MARKDOWN = auto()
    UNKNOWN = auto()


@dataclass
class Chunk:
    id: str
    content: str
    source_file: Path
    file_type: FileType
    page_number: int | None = None
    section_header: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_type: str = "text"


@dataclass
class ExtractionResult:
    chunks: list[Chunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class Extractor(ABC):
    """Base class for file extractors."""

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract chunks from a file.

        Args:
            file_path: Path to the file to extract.

        Returns:
            ExtractionResult containing chunks, metadata, and errors.
        """
        pass

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """Check if this extractor supports the given file.

        Args:
            file_path: Path to check.

        Returns:
            True if this extractor can handle the file, False otherwise.
        """
        pass

    @property
    @abstractmethod
    def file_type(self) -> FileType:
        """Return the file type this extractor handles."""
        pass
