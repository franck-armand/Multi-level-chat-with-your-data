from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from chatwithdocs.ingestion.base import Chunk, ExtractionResult, Extractor, FileType

logger = logging.getLogger(__name__)


class StructuredExtractor(Extractor):
    """Extract data from structured files (CSV, Excel) using pandas.

    This extractor handles:
    - CSV files with automatic delimiter detection
    - Excel files (.xlsx, .xls)
    - Table conversion to markdown format
    - Column names and data types in metadata
    """

    def __init__(self, max_rows_per_chunk: int = 100):
        self.max_rows_per_chunk = max_rows_per_chunk

    def extract(self, file_path: Path) -> ExtractionResult:
        """Extract content from structured file.

        Args:
            file_path: Path to CSV or Excel file.

        Returns:
            ExtractionResult with chunks and metadata.
        """
        try:
            import pandas as pd
        except ImportError:
            error_msg = "pandas not installed. Install with: uv pip install pandas"
            logger.error(error_msg)
            return ExtractionResult(errors=[error_msg])

        chunks: list[Chunk] = []
        errors: list[str] = []
        metadata: dict[str, Any] = {}

        suffix = file_path.suffix.lower()

        try:
            # Load data based on file type
            if suffix == ".csv":
                df = pd.read_csv(file_path)
                file_type = FileType.CSV
            elif suffix in [".xlsx", ".xls"]:
                df = pd.read_excel(file_path)
                file_type = FileType.EXCEL
            else:
                error_msg = f"Unsupported structured file format: {suffix}"
                logger.error(error_msg)
                return ExtractionResult(errors=[error_msg])

            # Store metadata about columns
            metadata = {
                "columns": df.columns.tolist(),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                "row_count": len(df),
                "file_type": suffix,
            }

            # Handle empty files
            if df.empty:
                logger.warning(f"Empty file: {file_path}")
                return ExtractionResult(metadata=metadata, errors=["File is empty"])

            # Convert entire table to markdown as first chunk
            full_table_chunk = self._dataframe_to_chunk(df, file_path, file_type, "full_table", 0)
            chunks.append(full_table_chunk)

            # Create row-based chunks for large tables
            if len(df) > self.max_rows_per_chunk:
                row_chunks = self._chunk_by_rows(df, file_path, file_type)
                chunks.extend(row_chunks)

        except Exception as e:
            error_msg = f"Error reading structured file {file_path}: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        return ExtractionResult(chunks=chunks, metadata=metadata, errors=errors)

    def _dataframe_to_chunk(
        self,
        df: Any,
        source_file: Path,
        file_type: FileType,
        chunk_type: str,
        chunk_index: int,
        row_start: int | None = None,
        row_end: int | None = None,
    ) -> Chunk:
        """Convert DataFrame to markdown table chunk.

        Args:
            df: pandas DataFrame (or slice).
            source_file: Source file path.
            file_type: File type (CSV or EXCEL).
            chunk_type: Type of chunk (full_table or row_chunk).
            chunk_index: Index of the chunk.
            row_start: Starting row number (optional).
            row_end: Ending row number (optional).

        Returns:
            Chunk with table in markdown format.
        """
        import pandas as pd

        lines = []

        # Header row
        header_cells = [str(col) for col in df.columns]
        lines.append("| " + " | ".join(header_cells) + " |")

        # Separator
        separators = ["---"] * len(header_cells)
        lines.append("| " + " | ".join(separators) + " |")

        # Data rows
        for _, row in df.iterrows():
            cells = [str(val) if pd.notna(val) else "" for val in row]
            lines.append("| " + " | ".join(cells) + " |")

        table_text = "\n".join(lines)

        # Build metadata
        chunk_metadata: dict[str, Any] = {
            "chunk_index": chunk_index,
            "chunk_type": chunk_type,
            "row_count": len(df),
        }

        if row_start is not None:
            chunk_metadata["row_start"] = row_start
        if row_end is not None:
            chunk_metadata["row_end"] = row_end

        return Chunk(
            id=str(uuid.uuid4()),
            content=f"Table ({chunk_type}):\n{table_text}",
            source_file=source_file,
            file_type=file_type,
            chunk_type="table",
            metadata=chunk_metadata,
        )

    def _chunk_by_rows(self, df: Any, source_file: Path, file_type: FileType) -> list[Chunk]:
        """Split large DataFrame into row-based chunks.

        Args:
            df: pandas DataFrame.
            source_file: Source file path.
            file_type: File type.

        Returns:
            List of chunks, each containing a subset of rows.
        """
        chunks: list[Chunk] = []
        total_rows = len(df)

        for i in range(0, total_rows, self.max_rows_per_chunk):
            end_idx = min(i + self.max_rows_per_chunk, total_rows)
            chunk_df = df.iloc[i:end_idx]

            chunk = self._dataframe_to_chunk(
                chunk_df,
                source_file,
                file_type,
                "row_chunk",
                len(chunks),
                row_start=i,
                row_end=end_idx - 1,
            )
            chunks.append(chunk)

        return chunks

    def supports(self, file_path: Path) -> bool:
        """Check if file is a supported structured format."""
        suffix = file_path.suffix.lower()
        return suffix in [".csv", ".xlsx", ".xls"]

    @property
    def file_type(self) -> FileType:
        """Return file type based on last extraction."""
        # This is dynamic, return UNKNOWN as default
        return FileType.UNKNOWN
