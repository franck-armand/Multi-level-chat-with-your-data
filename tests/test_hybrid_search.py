from __future__ import annotations

import asyncio
import uuid

from chatwithdocs.retrieval.hybrid_search import BM25Index, HybridSearcher
from chatwithdocs.storage.vectors import ChunkMetadata, SearchResult


class DummyEmbeddingResult:
    def __init__(self, embedding: list[float]):
        self.embedding = embedding


class DummyEmbedder:
    async def embed_query(self, query: str) -> DummyEmbeddingResult:
        return DummyEmbeddingResult([1.0, 0.0])


class DummyVectorStore:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name
        self._chunks: dict[str, tuple[str, dict]] = {}

    async def add_chunks(
        self,
        chunks: list[str],
        embeddings: list[list[float]],
        metadata: list[ChunkMetadata],
        ids: list[str] | None = None,
    ) -> list[str]:
        generated_ids = ids or [str(uuid.uuid4()) for _ in chunks]
        for chunk_id, chunk, meta in zip(generated_ids, chunks, metadata):
            self._chunks[chunk_id] = (
                chunk,
                {
                    "source_file": meta.source_file,
                    "file_type": meta.file_type,
                    "page_number": meta.page_number,
                    "section_header": meta.section_header,
                    "chunk_type": meta.chunk_type,
                    "user_id": meta.user_id,
                    **meta.custom,
                },
            )
        return generated_ids

    async def search(
        self,
        query_embedding: list[float],
        k: int = 10,
        filter_dict: dict | None = None,
    ) -> list[SearchResult]:
        return []

    async def delete_by_source(self, source_file: str) -> int:
        before = len(self._chunks)
        self._chunks = {
            chunk_id: payload
            for chunk_id, payload in self._chunks.items()
            if payload[1]["source_file"] != source_file
        }
        return before - len(self._chunks)

    async def delete_by_user(self, user_id: str) -> int:
        before = len(self._chunks)
        self._chunks = {
            chunk_id: payload
            for chunk_id, payload in self._chunks.items()
            if payload[1]["user_id"] != user_id
        }
        return before - len(self._chunks)


class TestHybridSearch:
    def setup_method(self):
        BM25Index.clear_shared()

    def teardown_method(self):
        BM25Index.clear_shared()

    def test_bm25_results_are_shared_across_searcher_instances(self):
        vector_store = DummyVectorStore("shared-hybrid-index")
        ingest_searcher = HybridSearcher(vector_store, DummyEmbedder())
        query_searcher = HybridSearcher(vector_store, DummyEmbedder())

        chunks = ["budget alpha report", "completely unrelated text"]
        metadata = [
            ChunkMetadata(source_file="report-a.txt", file_type="txt", user_id="alice"),
            ChunkMetadata(source_file="report-b.txt", file_type="txt", user_id="bob"),
        ]

        ids = asyncio.run(ingest_searcher.add_to_index(chunks, [[0.1], [0.2]], metadata))
        results = asyncio.run(query_searcher.search("alpha", filter_dict={"user_id": "alice"}))

        assert [result.id for result in results] == [ids[0]]
        assert results[0].bm25_score is not None
        assert results[0].metadata.user_id == "alice"

    def test_delete_by_user_removes_bm25_documents(self):
        vector_store = DummyVectorStore("delete-hybrid-index")
        ingest_searcher = HybridSearcher(vector_store, DummyEmbedder())
        query_searcher = HybridSearcher(vector_store, DummyEmbedder())

        asyncio.run(
            ingest_searcher.add_to_index(
                ["alpha budget note", "alpha second note"],
                [[0.1], [0.2]],
                [
                    ChunkMetadata(source_file="a.txt", file_type="txt", user_id="alice"),
                    ChunkMetadata(source_file="b.txt", file_type="txt", user_id="alice"),
                ],
            )
        )

        before_delete = asyncio.run(
            query_searcher.search("alpha", filter_dict={"user_id": "alice"})
        )
        assert len(before_delete) == 2

        deleted = asyncio.run(query_searcher.delete_by_user("alice"))
        after_delete = asyncio.run(query_searcher.search("alpha", filter_dict={"user_id": "alice"}))

        assert deleted == 2
        assert after_delete == []
