from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from chatwithdocs.chat.models import Citation, Message, MessageRole, Thread
from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


class ChatPersistence:
    """SQLite-based persistence for chat history."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or settings.chat_history_db
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Threads table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS threads (
                    id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata TEXT,
                    deleted BOOLEAN DEFAULT 0
                )
            """
            )

            # Messages table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
                )
            """
            )

            # Indexes
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_threads_user 
                ON threads(user_id, deleted)
            """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_thread 
                ON messages(thread_id, created_at)
            """
            )

            conn.commit()
            logger.info(f"Chat persistence initialized at {self.db_path}")

    def create_thread(self, thread: Thread) -> Thread:
        """Create a new thread."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO threads (id, user_id, title, created_at, updated_at, metadata, deleted)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    thread.id,
                    thread.user_id,
                    thread.title,
                    thread.created_at.isoformat(),
                    thread.updated_at.isoformat(),
                    json.dumps(thread.metadata),
                    False,
                ),
            )
            conn.commit()
            logger.debug(f"Created thread {thread.id}")
            return thread

    def get_thread(self, thread_id: str) -> Optional[Thread]:
        """Get a thread by ID with all its messages."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            # Get thread
            cursor.execute(
                """
                SELECT id, user_id, title, created_at, updated_at, metadata
                FROM threads
                WHERE id = ? AND deleted = 0
            """,
                (thread_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            thread = self._row_to_thread(row)

            # Get messages
            cursor.execute(
                """
                SELECT id, role, content, citations, metadata, created_at
                FROM messages
                WHERE thread_id = ?
                ORDER BY created_at ASC
            """,
                (thread_id,),
            )

            for msg_row in cursor.fetchall():
                message = self._row_to_message(msg_row)
                thread.messages.append(message)

            return thread

    def list_threads(
        self, user_id: str, limit: int = 50, include_deleted: bool = False
    ) -> List[Thread]:
        """List all threads for a user."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            if include_deleted:
                cursor.execute(
                    """
                    SELECT id, user_id, title, created_at, updated_at, metadata
                    FROM threads
                    WHERE user_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (user_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, user_id, title, created_at, updated_at, metadata
                    FROM threads
                    WHERE user_id = ? AND deleted = 0
                    ORDER BY updated_at DESC
                    LIMIT ?
                """,
                    (user_id, limit),
                )

            threads = []
            for row in cursor.fetchall():
                thread = self._row_to_thread(row)
                # Load first and last message for preview
                cursor.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE thread_id = ?
                    ORDER BY created_at ASC
                    LIMIT 1
                """,
                    (thread.id,),
                )
                first_msg = cursor.fetchone()
                if first_msg and not thread.title:
                    thread.generate_title(first_msg[1])

                threads.append(thread)

            return threads

    def update_thread(self, thread: Thread) -> Thread:
        """Update thread metadata."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE threads
                SET title = ?, updated_at = ?, metadata = ?
                WHERE id = ?
            """,
                (
                    thread.title,
                    thread.updated_at.isoformat(),
                    json.dumps(thread.metadata),
                    thread.id,
                ),
            )
            conn.commit()
            logger.debug(f"Updated thread {thread.id}")
            return thread

    def delete_thread(self, thread_id: str, soft: bool = True) -> bool:
        """Delete a thread (soft or hard delete)."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()

            if soft:
                cursor.execute(
                    """
                    UPDATE threads
                    SET deleted = 1, updated_at = ?
                    WHERE id = ?
                """,
                    (datetime.now(timezone.utc).isoformat(), thread_id),
                )
            else:
                cursor.execute("DELETE FROM messages WHERE thread_id = ?", (thread_id,))
                cursor.execute("DELETE FROM threads WHERE id = ?", (thread_id,))

            conn.commit()
            logger.debug(f"Deleted thread {thread_id} (soft={soft})")
            return cursor.rowcount > 0

    def add_message(self, thread_id: str, message: Message) -> Message:
        """Add a message to a thread."""
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO messages (id, thread_id, role, content, citations, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    message.id,
                    thread_id,
                    message.role.value,
                    message.content,
                    json.dumps([c.to_dict() for c in message.citations]),
                    json.dumps(message.metadata),
                    message.created_at.isoformat(),
                ),
            )

            # Update thread's updated_at
            cursor.execute(
                """
                UPDATE threads
                SET updated_at = ?
                WHERE id = ?
            """,
                (datetime.now(timezone.utc).isoformat(), thread_id),
            )

            conn.commit()
            logger.debug(f"Added message {message.id} to thread {thread_id}")
            return message

    def _row_to_thread(self, row: tuple) -> Thread:
        """Convert database row to Thread."""
        return Thread(
            id=row[0],
            user_id=row[1],
            title=row[2],
            created_at=datetime.fromisoformat(row[3]),
            updated_at=datetime.fromisoformat(row[4]),
            metadata=json.loads(row[5]) if row[5] else {},
        )

    def _row_to_message(self, row: tuple) -> Message:
        """Convert database row to Message."""
        citations = []
        if row[3]:  # citations JSON
            try:
                citation_data = json.loads(row[3])
                citations = [
                    Citation(
                        source_file=c["source_file"],
                        excerpt=c["excerpt"],
                        page_number=c.get("page_number"),
                        section=c.get("section"),
                        chunk_id=c.get("chunk_id"),
                        relevance_score=c.get("relevance_score"),
                    )
                    for c in citation_data
                ]
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse citations: {e}")

        return Message(
            id=row[0],
            role=MessageRole(row[1]),
            content=row[2],
            citations=citations,
            metadata=json.loads(row[4]) if row[4] else {},
            created_at=datetime.fromisoformat(row[5]),
        )

    def cleanup_old_threads(self, days: int = 30) -> int:
        """Permanently delete soft-deleted threads older than N days."""
        cutoff = datetime.now(timezone.utc) - __import__("datetime").timedelta(days=days)

        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM messages
                WHERE thread_id IN (
                    SELECT id FROM threads
                    WHERE deleted = 1 AND updated_at < ?
                )
            """,
                (cutoff.isoformat(),),
            )
            cursor.execute(
                """
                DELETE FROM threads
                WHERE deleted = 1 AND updated_at < ?
            """,
                (cutoff.isoformat(),),
            )
            conn.commit()
            return cursor.rowcount
