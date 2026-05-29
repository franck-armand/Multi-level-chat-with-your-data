from __future__ import annotations

import logging
from typing import List, Optional

from chatwithdocs.chat.models import Citation, Message, MessageRole, Thread
from chatwithdocs.chat.persistence import ChatPersistence

logger = logging.getLogger(__name__)


class ConversationManager:
    """High-level manager for chat conversations.

    Provides user-friendly methods for creating, managing, and deleting
    chat threads with proper persistence.
    """

    def __init__(self, persistence: ChatPersistence | None = None):
        self.persistence = persistence or ChatPersistence()

    def create_thread(self, user_id: str, title: Optional[str] = None) -> Thread:
        """Create a new conversation thread.

        Args:
            user_id: User identifier
            title: Optional thread title (auto-generated if not provided)

        Returns:
            New thread
        """
        thread = Thread(user_id=user_id, title=title)
        return self.persistence.create_thread(thread)

    def get_thread(self, thread_id: str) -> Optional[Thread]:
        """Get a thread by ID.

        Args:
            thread_id: Thread identifier

        Returns:
            Thread if found, None otherwise
        """
        return self.persistence.get_thread(thread_id)

    def list_conversations(self, user_id: str, limit: int = 50) -> List[dict]:
        """List conversations for a user.

        Returns lightweight conversation previews suitable for UI listing.

        Args:
            user_id: User identifier
            limit: Maximum number of conversations to return

        Returns:
            List of conversation summaries
        """
        threads = self.persistence.list_threads(user_id, limit=limit)

        summaries = []
        for thread in threads:
            # Get message count
            msg_count = len(thread.messages)

            # Get last message preview
            last_message = None
            if thread.messages:
                last = thread.messages[-1]
                last_message = {
                    "role": last.role.value,
                    "preview": last.content[:100] + "..."
                    if len(last.content) > 100
                    else last.content,
                }

            summaries.append(
                {
                    "id": thread.id,
                    "title": thread.title or "New Conversation",
                    "created_at": thread.created_at.isoformat(),
                    "updated_at": thread.updated_at.isoformat(),
                    "message_count": msg_count,
                    "last_message": last_message,
                }
            )

        return summaries

    def rename_thread(self, thread_id: str, new_title: str) -> Optional[Thread]:
        """Rename a conversation thread.

        Args:
            thread_id: Thread identifier
            new_title: New title

        Returns:
            Updated thread if found, None otherwise
        """
        thread = self.persistence.get_thread(thread_id)
        if not thread:
            return None

        thread.title = new_title
        return self.persistence.update_thread(thread)

    def delete_conversation(self, thread_id: str, user_id: str, permanent: bool = False) -> bool:
        """Delete a conversation.

        Args:
            thread_id: Thread identifier
            user_id: User identifier (for authorization)
            permanent: If True, permanently delete; otherwise soft delete

        Returns:
            True if deleted, False if not found or not authorized
        """
        thread = self.persistence.get_thread(thread_id)
        if not thread:
            return False

        # Check ownership
        if thread.user_id != user_id:
            logger.warning(
                f"User {user_id} attempted to delete thread {thread_id} owned by {thread.user_id}"
            )
            return False

        return self.persistence.delete_thread(thread_id, soft=not permanent)

    def add_user_message(self, thread_id: str, content: str) -> Optional[Message]:
        """Add a user message to a thread.

        Args:
            thread_id: Thread identifier
            content: Message content

        Returns:
            Created message if thread exists, None otherwise
        """
        thread = self.persistence.get_thread(thread_id)
        if not thread:
            return None

        # Auto-generate title on first message
        if not thread.title and not thread.messages:
            thread.generate_title(content)
            self.persistence.update_thread(thread)

        message = Message(role=MessageRole.USER, content=content)
        return self.persistence.add_message(thread_id, message)

    def add_assistant_message(
        self,
        thread_id: str,
        content: str,
        citations: Optional[List[Citation]] = None,
    ) -> Optional[Message]:
        """Add an assistant message to a thread.

        Args:
            thread_id: Thread identifier
            content: Message content
            citations: Optional list of citations

        Returns:
            Created message if thread exists, None otherwise
        """
        from chatwithdocs.chat.models import MessageRole

        thread = self.persistence.get_thread(thread_id)
        if not thread:
            return None

        message = Message(
            role=MessageRole.ASSISTANT,
            content=content,
            citations=citations or [],
        )
        return self.persistence.add_message(thread_id, message)

    def get_conversation_history(
        self, thread_id: str, limit: Optional[int] = None
    ) -> Optional[List[Message]]:
        """Get conversation history.

        Args:
            thread_id: Thread identifier
            limit: Maximum number of recent messages to return

        Returns:
            List of messages if thread exists, None otherwise
        """
        thread = self.persistence.get_thread(thread_id)
        if not thread:
            return None

        messages = thread.messages
        if limit:
            messages = messages[-limit:]

        return messages

    def cleanup_deleted_conversations(self, days: int = 30) -> int:
        """Permanently delete old soft-deleted conversations.

        Args:
            days: Age in days before permanent deletion

        Returns:
            Number of conversations deleted
        """
        return self.persistence.cleanup_old_threads(days=days)
