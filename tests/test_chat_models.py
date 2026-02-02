from __future__ import annotations

from datetime import datetime

from chatwithdocs.chat import Citation, Message, MessageRole, Thread


class TestCitation:
    """Test suite for Citation model."""

    def test_citation_creation(self):
        """Test creating a citation."""
        citation = Citation(
            source_file="test.pdf",
            excerpt="This is a test excerpt",
            page_number=5,
            section="Introduction",
        )
        assert citation.source_file == "test.pdf"
        assert citation.excerpt == "This is a test excerpt"
        assert citation.page_number == 5
        assert citation.section == "Introduction"

    def test_citation_to_dict(self):
        """Test citation serialization."""
        citation = Citation(source_file="doc.pdf", excerpt="test", relevance_score=0.95)
        data = citation.to_dict()
        assert data["source_file"] == "doc.pdf"
        assert data["excerpt"] == "test"
        assert data["relevance_score"] == 0.95
        assert data["page_number"] is None


class TestMessage:
    """Test suite for Message model."""

    def test_message_creation(self):
        """Test creating a message."""
        message = Message(role=MessageRole.USER, content="Hello, world!")
        assert message.role == MessageRole.USER
        assert message.content == "Hello, world!"
        assert message.citations == []
        assert isinstance(message.id, str)
        assert isinstance(message.created_at, datetime)

    def test_message_with_citations(self):
        """Test message with citations."""
        citation = Citation(source_file="test.pdf", excerpt="test")
        message = Message(
            role=MessageRole.ASSISTANT, content="Answer with citation", citations=[citation]
        )
        assert len(message.citations) == 1
        assert message.citations[0].source_file == "test.pdf"

    def test_message_serialization(self):
        """Test message to_dict and from_dict."""
        citation = Citation(source_file="doc.pdf", excerpt="quote", page_number=10)
        original = Message(
            role=MessageRole.ASSISTANT,
            content="Response",
            citations=[citation],
            metadata={"confidence": 0.9},
        )

        data = original.to_dict()
        restored = Message.from_dict(data)

        assert restored.role == original.role
        assert restored.content == original.content
        assert restored.metadata == original.metadata
        assert len(restored.citations) == 1
        assert restored.citations[0].page_number == 10


class TestThread:
    """Test suite for Thread model."""

    def test_thread_creation(self):
        """Test creating a thread."""
        thread = Thread(user_id="user123")
        assert thread.user_id == "user123"
        assert thread.title is None
        assert thread.messages == []
        assert isinstance(thread.id, str)

    def test_add_message(self):
        """Test adding messages to thread."""
        thread = Thread(user_id="user1")
        message = Message(role=MessageRole.USER, content="Hello")

        thread.add_message(message)

        assert len(thread.messages) == 1
        assert thread.messages[0].content == "Hello"
        assert thread.updated_at >= thread.created_at

    def test_get_last_n_messages(self):
        """Test retrieving last N messages."""
        thread = Thread(user_id="user1")

        for i in range(5):
            thread.add_message(Message(role=MessageRole.USER, content=f"Msg {i}"))

        last_3 = thread.get_last_n_messages(3)
        assert len(last_3) == 3
        assert last_3[-1].content == "Msg 4"

    def test_generate_title(self):
        """Test title generation from first message."""
        thread = Thread(user_id="user1")
        thread.generate_title("This is a very long message that should be truncated")

        assert thread.title is not None
        assert len(thread.title) <= 53  # 50 chars + "..."
        assert "..." in thread.title

    def test_thread_serialization(self):
        """Test thread to_dict and from_dict."""
        thread = Thread(user_id="user1", title="Test Thread")
        thread.add_message(Message(role=MessageRole.USER, content="Hello"))
        thread.add_message(Message(role=MessageRole.ASSISTANT, content="Hi!"))

        data = thread.to_dict()
        restored = Thread.from_dict(data)

        assert restored.user_id == thread.user_id
        assert restored.title == thread.title
        assert len(restored.messages) == 2
        assert restored.messages[0].role == MessageRole.USER
