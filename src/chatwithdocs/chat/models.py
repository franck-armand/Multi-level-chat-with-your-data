from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
import uuid


class MessageRole(str, Enum):
    """Role of a message in the conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


@dataclass
class Citation:
    """Citation for a piece of information in a response."""

    source_file: str
    excerpt: str
    page_number: Optional[int] = None
    section: Optional[str] = None
    chunk_id: Optional[str] = None
    relevance_score: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "source_file": self.source_file,
            "excerpt": self.excerpt,
            "page_number": self.page_number,
            "section": self.section,
            "chunk_id": self.chunk_id,
            "relevance_score": self.relevance_score,
        }


@dataclass
class Message:
    """A message in a chat conversation."""

    role: MessageRole
    content: str
    citations: List[Citation] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "role": self.role.value,
            "content": self.content,
            "citations": [c.to_dict() for c in self.citations],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        """Create from dictionary."""
        citations = [
            Citation(
                source_file=c["source_file"],
                excerpt=c["excerpt"],
                page_number=c.get("page_number"),
                section=c.get("section"),
                chunk_id=c.get("chunk_id"),
                relevance_score=c.get("relevance_score"),
            )
            for c in data.get("citations", [])
        ]
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            role=MessageRole(data["role"]),
            content=data["content"],
            citations=citations,
            metadata=data.get("metadata", {}),
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(timezone.utc),
        )


@dataclass
class Thread:
    """A chat conversation thread."""

    user_id: str
    title: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_message(self, message: Message) -> None:
        """Add a message to the thread."""
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc)

    def get_last_n_messages(self, n: int) -> List[Message]:
        """Get last n messages."""
        return self.messages[-n:] if n > 0 else []

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "messages": [m.to_dict() for m in self.messages],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Thread":
        """Create from dictionary."""
        messages = [Message.from_dict(m) for m in data.get("messages", [])]
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            user_id=data["user_id"],
            title=data.get("title"),
            messages=messages,
            created_at=datetime.fromisoformat(data["created_at"])
            if "created_at" in data
            else datetime.now(timezone.utc),
            updated_at=datetime.fromisoformat(data["updated_at"])
            if "updated_at" in data
            else datetime.now(timezone.utc),
            metadata=data.get("metadata", {}),
        )

    def generate_title(self, first_message: str) -> None:
        """Generate a title from the first user message."""
        if not self.title and first_message:
            # Simple title generation - first 50 chars
            title = first_message.strip()[:50]
            if len(first_message) > 50:
                title += "..."
            self.title = title
