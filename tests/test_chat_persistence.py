from __future__ import annotations

import tempfile
from pathlib import Path

from chatwithdocs.chat.persistence import ChatPersistence
from chatwithdocs.chat.models import Thread, Message, MessageRole, Citation


class TestChatPersistence:
    """Test suite for chat persistence."""

    def test_create_thread(self):
        """Test creating a thread in database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            persistence = ChatPersistence(db_path)

            thread = Thread(user_id="user1", title="Test Thread")
            created = persistence.create_thread(thread)

            assert created.id == thread.id
            assert created.user_id == "user1"

    def test_get_thread(self):
        """Test retrieving a thread with messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            persistence = ChatPersistence(db_path)

            # Create thread
            thread = Thread(user_id="user1", title="Test")
            persistence.create_thread(thread)

            # Add messages
            msg1 = Message(role=MessageRole.USER, content="Hello")
            msg2 = Message(role=MessageRole.ASSISTANT, content="Hi there!")
            persistence.add_message(thread.id, msg1)
            persistence.add_message(thread.id, msg2)

            # Retrieve
            retrieved = persistence.get_thread(thread.id)
            assert retrieved is not None
            assert retrieved.title == "Test"
            assert len(retrieved.messages) == 2
            assert retrieved.messages[0].content == "Hello"
            assert retrieved.messages[1].role == MessageRole.ASSISTANT

    def test_list_threads(self):
        """Test listing threads for a user."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            persistence = ChatPersistence(db_path)

            # Create threads
            thread1 = Thread(user_id="user1", title="Thread 1")
            thread2 = Thread(user_id="user1", title="Thread 2")
            thread3 = Thread(user_id="user2", title="Thread 3")

            persistence.create_thread(thread1)
            persistence.create_thread(thread2)
            persistence.create_thread(thread3)

            # List for user1
            threads = persistence.list_threads("user1")
            assert len(threads) == 2
            titles = [t.title for t in threads]
            assert "Thread 1" in titles
            assert "Thread 2" in titles

    def test_delete_thread_soft(self):
        """Test soft deleting a thread."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            persistence = ChatPersistence(db_path)

            thread = Thread(user_id="user1", title="To Delete")
            persistence.create_thread(thread)

            # Soft delete
            result = persistence.delete_thread(thread.id, soft=True)
            assert result is True

            # Should not be in normal list
            threads = persistence.list_threads("user1")
            assert len(threads) == 0

            # Should be in list with deleted
            threads = persistence.list_threads("user1", include_deleted=True)
            assert len(threads) == 1

    def test_citation_persistence(self):
        """Test that citations are properly saved and loaded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            persistence = ChatPersistence(db_path)

            thread = Thread(user_id="user1")
            persistence.create_thread(thread)

            # Add message with citations
            citation = Citation(
                source_file="doc.pdf",
                excerpt="Test excerpt",
                page_number=5,
                section="Introduction",
                relevance_score=0.95,
            )
            msg = Message(
                role=MessageRole.ASSISTANT, content="Answer with citation", citations=[citation]
            )
            persistence.add_message(thread.id, msg)

            # Retrieve and check
            retrieved = persistence.get_thread(thread.id)
            assert len(retrieved.messages) == 1
            assert len(retrieved.messages[0].citations) == 1
            assert retrieved.messages[0].citations[0].source_file == "doc.pdf"
            assert retrieved.messages[0].citations[0].page_number == 5
