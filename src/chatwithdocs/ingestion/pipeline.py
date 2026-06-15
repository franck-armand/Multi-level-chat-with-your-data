from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from chatwithdocs.chat.models_doc import Document
from chatwithdocs.embedding import EmbeddingRouter
from chatwithdocs.ingestion.base import Chunk, Extractor
from chatwithdocs.ingestion.extractors.docx import DOCXExtractor
from chatwithdocs.ingestion.extractors.marker import MarkerPDFExtractor
from chatwithdocs.ingestion.extractors.pdf import PDFExtractor
from chatwithdocs.ingestion.extractors.structured import StructuredExtractor
from chatwithdocs.ingestion.extractors.text import TextExtractor
from chatwithdocs.retrieval import HybridSearcher
from chatwithdocs.security import FileSandbox
from chatwithdocs.security.audit import audit_logger
from chatwithdocs.storage.document_registry import DocumentRegistry
from chatwithdocs.storage.vectors import ChromaVectorStore, ChunkMetadata

logger = logging.getLogger(__name__)


class IngestionPipeline:
    """End-to-end ingestion pipeline for documents.

    Orchestrates the flow:
    1. File validation and sandboxing
    2. Content extraction
    3. Chunking
    4. Embedding generation
    5. Vector storage
    6. Document registration
    7. Audit logging
    """

    def __init__(
        self,
        vector_store: ChromaVectorStore | None = None,
        embedder: EmbeddingRouter | None = None,
        sandbox: FileSandbox | None = None,
        doc_registry: DocumentRegistry | None = None,
    ):
        self.vector_store = vector_store or ChromaVectorStore()
        self.embedder = embedder or EmbeddingRouter()
        self.hybrid_searcher = HybridSearcher(self.vector_store, self.embedder)
        self.sandbox = sandbox or FileSandbox()
        self.doc_registry = doc_registry or DocumentRegistry()

        # Register extractors
        self._extractors: list[Extractor] = [
            MarkerPDFExtractor(),
            PDFExtractor(),
            DOCXExtractor(),
            StructuredExtractor(),
            TextExtractor(),
        ]

    async def ingest_file(
        self,
        file_path: Path,
        user_id: str,
    ) -> dict[str, Any]:
        """Ingest a file through the complete pipeline.

        Args:
            file_path: Path to file to ingest
            user_id: User uploading the file

        Returns:
            Dictionary with ingestion results
        """
        logger.info(f"Starting ingestion for {file_path} (user: {user_id})")

        # Step 1: Sandbox and validate
        try:
            sandbox_result = self.sandbox.process_file(file_path, user_id)
            if not sandbox_result.is_safe:
                error_msg = sandbox_result.error_message or "File failed security check"
                logger.error(error_msg)
                audit_logger.log_file_upload(
                    user_id=user_id,
                    filename=file_path.name,
                    file_hash="",
                    file_size=0,
                    success=False,
                    error=error_msg,
                )
                return {
                    "success": False,
                    "error": error_msg,
                    "chunks_indexed": 0,
                }

            # Use sanitized path
            processed_path = sandbox_result.sanitized_path or file_path
            logger.info(f"File sandboxed: {processed_path}")

        except Exception as e:
            error_msg = f"Sandbox processing failed: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "chunks_indexed": 0,
            }

        # Step 1b: Dedup check — skip if same hash already registered for this user
        file_hash = sandbox_result.original_hash or ""
        file_size = processed_path.stat().st_size if processed_path.exists() else 0
        if file_hash:
            existing = self.doc_registry.find_by_hash(user_id, file_hash)
            if existing:
                logger.info(
                    f"Duplicate document detected: {existing.filename} (doc_id={existing.id})"
                )
                audit_logger.log_file_upload(
                    user_id=user_id,
                    filename=file_path.name,
                    file_hash=file_hash,
                    file_size=file_size,
                    success=True,
                )
                return {
                    "success": True,
                    "duplicate": True,
                    "doc_id": existing.id,
                    "file_path": existing.file_path,
                    "chunks_indexed": 0,
                }

        # Step 2: Extract content
        try:
            extractor = self._get_extractor(processed_path)
            if not extractor:
                error_msg = f"No extractor found for {processed_path.suffix}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "chunks_indexed": 0,
                }

            extraction_result = extractor.extract(processed_path)

            if extraction_result.errors and not extraction_result.chunks:
                error_msg = f"Extraction failed: {extraction_result.errors[0]}"
                logger.error(error_msg)
                return {
                    "success": False,
                    "error": error_msg,
                    "chunks_indexed": 0,
                }

            logger.info(f"Extracted {len(extraction_result.chunks)} chunks")

        except Exception as e:
            error_msg = f"Content extraction failed: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "chunks_indexed": 0,
            }

        # Step 3: Register document before indexing (so we have doc_id for chunks)
        doc = Document(
            user_id=user_id,
            filename=file_path.name,
            file_hash=file_hash,
            file_path=str(processed_path),
            file_size=file_size,
            file_type=processed_path.suffix.lstrip(".").lower(),
        )
        self.doc_registry.register(doc)
        doc_id = doc.id

        # Step 4: Generate embeddings and store
        try:
            chunks_indexed = await self._index_chunks(
                extraction_result.chunks, user_id, doc_id=doc_id
            )
            self.doc_registry.update_chunk_count(doc_id, chunks_indexed)
            logger.info(f"Indexed {chunks_indexed} chunks for doc {doc_id}")

        except Exception as e:
            error_msg = f"Indexing failed: {e}"
            logger.error(error_msg)
            # Clean up the document record on failure
            self.doc_registry.delete(doc_id)
            return {
                "success": False,
                "error": error_msg,
                "chunks_indexed": 0,
            }

        # Step 5: Audit logging
        audit_logger.log_file_upload(
            user_id=user_id,
            filename=file_path.name,
            file_hash=file_hash,
            file_size=file_size,
            success=True,
        )

        return {
            "success": True,
            "doc_id": doc_id,
            "file_path": str(processed_path),
            "chunks_indexed": chunks_indexed,
            "metadata": extraction_result.metadata,
            "errors": extraction_result.errors,
        }

    def _get_extractor(self, file_path: Path) -> Extractor | None:
        """Get appropriate extractor for file type."""
        for extractor in self._extractors:
            if extractor.supports(file_path):
                return extractor
        return None

    async def _index_chunks(
        self, chunks: list[Chunk], user_id: str, doc_id: str | None = None
    ) -> int:
        """Index chunks by generating embeddings and storing in vector DB.

        Args:
            chunks: List of chunks to index
            user_id: User ID for metadata
            doc_id: Optional document ID to link chunks

        Returns:
            Number of chunks indexed
        """
        if not chunks:
            return 0

        # Prepare data for batch processing
        texts = [chunk.content for chunk in chunks]

        # Generate embeddings
        embedding_results = await self.embedder.embed(texts)
        embeddings = [result.embedding for result in embedding_results]

        # Convert to storage format
        storage_chunks = []
        metadata_list = []

        for chunk in chunks:
            storage_chunks.append(chunk.content)
            metadata_list.append(
                ChunkMetadata(
                    source_file=str(chunk.source_file),
                    file_type=chunk.file_type.name if chunk.file_type else "unknown",
                    page_number=chunk.page_number,
                    section_header=chunk.section_header,
                    chunk_type=chunk.chunk_type,
                    user_id=user_id,
                    doc_id=doc_id,
                    custom=chunk.metadata,
                )
            )

        # Store in vector DB
        ids = await self.hybrid_searcher.add_to_index(storage_chunks, embeddings, metadata_list)

        return len(ids)

    async def delete_file(self, source_file: str) -> bool:
        """Delete all chunks for a source file.

        Args:
            source_file: Source file path

        Returns:
            True if deleted, False otherwise
        """
        try:
            await self.hybrid_searcher.delete_by_source(source_file)
            logger.info(f"Deleted all chunks for {source_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete chunks for {source_file}: {e}")
            return False

    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document and all its chunks.

        Removes chunks from vector store + BM25, deletes the file from disk,
        and removes the document record from the registry.

        Args:
            doc_id: Document ID to delete

        Returns:
            True if deleted, False otherwise
        """
        try:
            doc = self.doc_registry.get(doc_id)
            if not doc:
                logger.warning(f"Document {doc_id} not found in registry")
                return False

            # Remove chunks from vector store and BM25
            await self.hybrid_searcher.delete_by_doc_id(doc_id)

            # Remove file from disk
            file_path = Path(doc.file_path)
            if file_path.exists():
                file_path.unlink()
                logger.info(f"Deleted file: {file_path}")

            # Remove document record (cascades collection_documents)
            self.doc_registry.delete(doc_id)

            logger.info(f"Deleted document {doc_id} ({doc.filename})")
            return True
        except Exception as e:
            logger.error(f"Failed to delete document {doc_id}: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """Get ingestion pipeline statistics."""
        # This would need to be async to get real stats from vector store
        return {
            "supported_formats": [
                ".pdf",
                ".docx",
                ".csv",
                ".xlsx",
                ".xls",
                ".txt",
                ".md",
                ".markdown",
            ],
            "chunk_size": 1000,
            "chunk_overlap": 200,
        }
