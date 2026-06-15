from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from chatwithdocs.chat.models_doc import Collection, Document
from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


class DocumentRegistry:
    """SQLite-based registry for tracking uploaded documents.

    Shares the same database as ChatPersistence (data/chat_history.db).
    """

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.chat_history_db
        self._init_db()

    def _init_db(self) -> None:
        """Initialize document registry tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    file_type TEXT NOT NULL DEFAULT '',
                    chunk_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    owner_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS collection_documents (
                    collection_id TEXT NOT NULL,
                    doc_id TEXT NOT NULL,
                    added_at TEXT NOT NULL,
                    PRIMARY KEY (collection_id, doc_id),
                    FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                    FOREIGN KEY (doc_id) REFERENCES documents(id) ON DELETE CASCADE
                )
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_user
                ON documents(user_id)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_documents_hash
                ON documents(user_id, file_hash)
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_collections_owner
                ON collections(owner_id)
            """
            )

            conn.commit()
            logger.info(f"Document registry initialized at {self.db_path}")

    # ---- Document CRUD ----

    def register(self, document: Document) -> Document:
        """Register a new document."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO documents (id, user_id, filename, file_hash, file_path,
                                       file_size, file_type, chunk_count, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    document.id,
                    document.user_id,
                    document.filename,
                    document.file_hash,
                    document.file_path,
                    document.file_size,
                    document.file_type,
                    document.chunk_count,
                    document.created_at.isoformat(),
                    document.updated_at.isoformat(),
                ),
            )
            conn.commit()
            logger.debug(f"Registered document {document.id} ({document.filename})")
            return document

    def get(self, doc_id: str) -> Optional[Document]:
        """Get a document by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, user_id, filename, file_hash, file_path, file_size, "
                "file_type, chunk_count, created_at, updated_at "
                "FROM documents WHERE id = ?",
                (doc_id,),
            )
            row = cursor.fetchone()
            return self._row_to_document(row) if row else None

    def list_by_user(self, user_id: str) -> List[Document]:
        """List all documents for a user."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, user_id, filename, file_hash, file_path, file_size, "
                "file_type, chunk_count, created_at, updated_at "
                "FROM documents WHERE user_id = ? "
                "ORDER BY created_at DESC",
                (user_id,),
            )
            return [self._row_to_document(row) for row in cursor.fetchall()]

    def find_by_hash(self, user_id: str, file_hash: str) -> Optional[Document]:
        """Find a document by its content hash for a given user (dedup)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, user_id, filename, file_hash, file_path, file_size, "
                "file_type, chunk_count, created_at, updated_at "
                "FROM documents WHERE user_id = ? AND file_hash = ?",
                (user_id, file_hash),
            )
            row = cursor.fetchone()
            return self._row_to_document(row) if row else None

    def update_chunk_count(self, doc_id: str, chunk_count: int) -> None:
        """Update the chunk count for a document."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE documents SET chunk_count = ?, updated_at = ? WHERE id = ?",
                (chunk_count, datetime.now(timezone.utc).isoformat(), doc_id),
            )
            conn.commit()

    def delete(self, doc_id: str) -> bool:
        """Delete a document record."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            # Remove from any collections
            cursor.execute("DELETE FROM collection_documents WHERE doc_id = ?", (doc_id,))
            # Delete the document record
            cursor.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.debug(f"Deleted document record {doc_id}")
            return deleted

    # ---- Collection CRUD ----

    def create_collection(self, collection: Collection) -> Collection:
        """Create a new collection."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO collections (id, name, description, owner_id, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    collection.id,
                    collection.name,
                    collection.description,
                    collection.owner_id,
                    collection.created_at.isoformat(),
                    collection.updated_at.isoformat(),
                ),
            )
            conn.commit()
            logger.debug(f"Created collection {collection.id} ({collection.name})")
            return collection

    def get_collection(self, collection_id: str) -> Optional[Collection]:
        """Get a collection by ID."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, description, owner_id, created_at, updated_at "
                "FROM collections WHERE id = ?",
                (collection_id,),
            )
            row = cursor.fetchone()
            return self._row_to_collection(row) if row else None

    def list_collections(self, owner_id: str) -> List[Collection]:
        """List all collections for a user."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, description, owner_id, created_at, updated_at "
                "FROM collections WHERE owner_id = ? "
                "ORDER BY created_at DESC",
                (owner_id,),
            )
            return [self._row_to_collection(row) for row in cursor.fetchall()]

    def add_doc_to_collection(self, collection_id: str, doc_id: str) -> bool:
        """Add a document to a collection."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO collection_documents (collection_id, doc_id, added_at) "
                    "VALUES (?, ?, ?)",
                    (collection_id, doc_id, datetime.now(timezone.utc).isoformat()),
                )
                conn.commit()
                # Update collection's updated_at
                cursor.execute(
                    "UPDATE collections SET updated_at = ? WHERE id = ?",
                    (datetime.now(timezone.utc).isoformat(), collection_id),
                )
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                logger.warning(f"Document {doc_id} already in collection {collection_id}")
                return False

    def remove_doc_from_collection(self, collection_id: str, doc_id: str) -> bool:
        """Remove a document from a collection."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM collection_documents WHERE collection_id = ? AND doc_id = ?",
                (collection_id, doc_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_collection_doc_ids(self, collection_id: str) -> List[str]:
        """Get all document IDs in a collection."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT doc_id FROM collection_documents "
                "WHERE collection_id = ? ORDER BY added_at ASC",
                (collection_id,),
            )
            return [row[0] for row in cursor.fetchall()]

    def delete_collection(self, collection_id: str) -> bool:
        """Delete a collection and its document associations."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM collection_documents WHERE collection_id = ?",
                (collection_id,),
            )
            cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            conn.commit()
            return cursor.rowcount > 0

    # ---- Helpers ----

    def _row_to_document(self, row: tuple) -> Document:
        return Document(
            id=row[0],
            user_id=row[1],
            filename=row[2],
            file_hash=row[3],
            file_path=row[4],
            file_size=row[5],
            file_type=row[6],
            chunk_count=row[7],
            created_at=datetime.fromisoformat(row[8]),
            updated_at=datetime.fromisoformat(row[9]),
        )

    def _row_to_collection(self, row: tuple) -> Collection:
        return Collection(
            id=row[0],
            name=row[1],
            description=row[2] or "",
            owner_id=row[3],
            created_at=datetime.fromisoformat(row[4]),
            updated_at=datetime.fromisoformat(row[5]),
        )
