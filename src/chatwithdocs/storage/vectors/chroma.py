from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from chatwithdocs.config import settings
from chatwithdocs.storage.vectors.base import ChunkMetadata, SearchResult, VectorStore

logger = logging.getLogger(__name__)


class ChromaVectorStore(VectorStore):
    """ChromaDB vector store implementation.

    Uses ChromaDB as the backend for storing and searching vector embeddings.
    Supports persistent storage and metadata filtering.
    """

    def __init__(self, collection_name: str = "chatwithdocs_chunks"):
        """Initialize ChromaDB vector store.

        Args:
            collection_name: Name of the collection to use
        """
        self.collection_name = collection_name
        self._client: Optional[chromadb.ClientAPI] = None
        self._collection: Optional[chromadb.Collection] = None

    def _get_client(self) -> chromadb.ClientAPI:
        """Get or create ChromaDB client with lazy initialization.

        Returns:
            ChromaDB client instance
        """
        if self._client is None:
            chroma_path = settings.get_chroma_path()
            logger.info(f"Initializing ChromaDB at: {chroma_path}")

            self._client = chromadb.PersistentClient(
                path=str(chroma_path),
                settings=ChromaSettings(
                    anonymized_telemetry=False,
                    allow_reset=True,
                ),
            )

            # Get or create collection
            self._collection = self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"Using collection: {self.collection_name}")

        return self._client

    def _get_collection(self) -> chromadb.Collection:
        """Get the collection, initializing client if needed.

        Returns:
            ChromaDB collection instance
        """
        if self._collection is None:
            self._get_client()
        return self._collection

    def _metadata_to_dict(self, metadata: ChunkMetadata) -> Dict[str, Any]:
        """Convert ChunkMetadata to flat dict for ChromaDB.

        ChromaDB requires flat metadata structures without nested dicts.

        Args:
            metadata: ChunkMetadata instance

        Returns:
            Flat dictionary for ChromaDB storage
        """
        result = {
            "source_file": metadata.source_file,
            "file_type": metadata.file_type,
            "chunk_type": metadata.chunk_type,
        }

        if metadata.page_number is not None:
            result["page_number"] = metadata.page_number

        if metadata.section_header is not None:
            result["section_header"] = metadata.section_header

        if metadata.user_id is not None:
            result["user_id"] = metadata.user_id

        # Flatten custom metadata with prefix to avoid collisions
        for key, value in metadata.custom.items():
            result[f"custom_{key}"] = value

        return result

    def _dict_to_metadata(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ChromaDB metadata dict back to standard format.

        Args:
            data: Metadata dict from ChromaDB

        Returns:
            Reconstructed metadata dict
        """
        result = dict(data)

        # Extract custom metadata
        custom = {}
        keys_to_remove = []
        for key, value in result.items():
            if key.startswith("custom_"):
                custom[key[7:]] = value  # Remove 'custom_' prefix
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del result[key]

        if custom:
            result["custom"] = custom

        return result

    async def add_chunks(
        self,
        chunks: List[str],
        embeddings: List[List[float]],
        metadata: List[ChunkMetadata],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Add chunks with embeddings to the store.

        Args:
            chunks: List of text chunks
            embeddings: List of embedding vectors
            metadata: List of metadata for each chunk
            ids: Optional list of IDs (auto-generated if not provided)

        Returns:
            List of IDs for added chunks
        """
        if not chunks:
            return []

        if len(chunks) != len(embeddings) or len(chunks) != len(metadata):
            raise ValueError("chunks, embeddings, and metadata must have the same length")

        # Generate IDs if not provided
        if ids is None:
            ids = [str(uuid.uuid4()) for _ in chunks]

        # Convert metadata to ChromaDB format
        chroma_metadata = [self._metadata_to_dict(m) for m in metadata]

        # Get collection (may initialize client)
        collection = self._get_collection()

        # Add to ChromaDB (CPU-bound operation, use thread pool)
        import asyncio

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: collection.add(
                ids=ids,
                documents=chunks,
                embeddings=embeddings,
                metadatas=chroma_metadata,
            ),
        )

        logger.info(f"Added {len(chunks)} chunks to collection '{self.collection_name}'")
        return ids

    async def search(
        self,
        query_embedding: List[float],
        k: int = 10,
        filter_dict: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Search for similar chunks.

        Args:
            query_embedding: Query embedding vector
            k: Number of results to return
            filter_dict: Optional metadata filters

        Returns:
            List of search results
        """
        collection = self._get_collection()

        # Build where clause from filter_dict
        where_clause = None
        if filter_dict:
            where_clause = self._build_where_clause(filter_dict)

        # Query ChromaDB
        import asyncio

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            ),
        )

        # Convert to SearchResult objects
        search_results = []
        if results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                content = results["documents"][0][i] if results["documents"] else ""
                distance = results["distances"][0][i] if results["distances"] else 0.0
                metadata = (
                    self._dict_to_metadata(results["metadatas"][0][i])
                    if results["metadatas"]
                    else {}
                )

                # Convert cosine distance to similarity score (1 - distance)
                score = 1.0 - distance

                search_results.append(
                    SearchResult(
                        id=chunk_id,
                        content=content,
                        score=score,
                        metadata=metadata,
                    )
                )

        return search_results

    def _build_where_clause(self, filter_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Build ChromaDB where clause from filter dict.

        Args:
            filter_dict: Filter dictionary with field -> value mappings

        Returns:
            ChromaDB where clause dict or None
        """
        if not filter_dict:
            return None

        # ChromaDB supports simple equality filters and logical operators
        # For now, support simple equality and basic operators
        where_clause = {}

        for key, value in filter_dict.items():
            if isinstance(value, dict):
                # Handle operator filters (e.g., {"$gte": 5})
                where_clause[key] = value
            else:
                # Simple equality
                where_clause[key] = value

        return where_clause if where_clause else None

    async def delete_by_user(self, user_id: str) -> int:
        """Delete all chunks belonging to a user.

        Args:
            user_id: User identifier

        Returns:
            Number of chunks deleted
        """
        collection = self._get_collection()

        # First, find all matching IDs
        import asyncio

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: collection.get(
                where={"user_id": user_id},
                include=[],
            ),
        )

        if not results["ids"]:
            logger.info(f"No chunks found for user: {user_id}")
            return 0

        # Delete the chunks
        ids_to_delete = results["ids"]
        await loop.run_in_executor(
            None,
            lambda: collection.delete(ids=ids_to_delete),
        )

        logger.info(f"Deleted {len(ids_to_delete)} chunks for user: {user_id}")
        return len(ids_to_delete)

    async def delete_by_source(self, source_file: str) -> int:
        """Delete all chunks from a source file.

        Args:
            source_file: Source file path

        Returns:
            Number of chunks deleted
        """
        collection = self._get_collection()

        # First, find all matching IDs
        import asyncio

        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(
            None,
            lambda: collection.get(
                where={"source_file": source_file},
                include=[],
            ),
        )

        if not results["ids"]:
            return 0

        # Delete the chunks
        ids_to_delete = results["ids"]
        await loop.run_in_executor(
            None,
            lambda: collection.delete(ids=ids_to_delete),
        )

        logger.info(f"Deleted {len(ids_to_delete)} chunks from source: {source_file}")
        return len(ids_to_delete)

    async def delete_by_id(self, chunk_id: str) -> bool:
        """Delete a chunk by ID.

        Args:
            chunk_id: Chunk ID

        Returns:
            True if deleted, False if not found
        """
        collection = self._get_collection()

        import asyncio

        loop = asyncio.get_event_loop()

        # Check if chunk exists
        try:
            result = await loop.run_in_executor(
                None,
                lambda: collection.get(ids=[chunk_id], include=[]),
            )
            if not result["ids"]:
                return False
        except Exception:
            return False

        # Delete the chunk
        await loop.run_in_executor(
            None,
            lambda: collection.delete(ids=[chunk_id]),
        )

        logger.info(f"Deleted chunk: {chunk_id}")
        return True

    async def get_stats(self) -> Dict[str, Any]:
        """Get store statistics.

        Returns:
            Dictionary with stats (total_chunks, etc.)
        """
        collection = self._get_collection()

        import asyncio

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: collection.count(),
        )

        return {
            "total_chunks": result,
            "collection_name": self.collection_name,
            "vector_store_type": "chroma",
        }

    async def clear(self) -> None:
        """Clear all data from the store."""
        client = self._get_client()

        import asyncio

        loop = asyncio.get_event_loop()

        # Delete and recreate the collection
        try:
            await loop.run_in_executor(
                None,
                lambda: client.delete_collection(name=self.collection_name),
            )
            logger.info(f"Deleted collection: {self.collection_name}")
        except Exception as e:
            logger.warning(f"Error deleting collection (may not exist): {e}")

        # Recreate collection
        self._collection = await loop.run_in_executor(
            None,
            lambda: client.create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            ),
        )

        logger.info(f"Recreated empty collection: {self.collection_name}")
