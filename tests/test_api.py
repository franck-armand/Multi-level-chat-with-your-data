from __future__ import annotations

import importlib.util
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from chatwithdocs.chat.manager import ConversationManager
from chatwithdocs.chat.persistence import ChatPersistence
from chatwithdocs.security import PromptInjectionDetector


API_MAIN_PATH = Path(__file__).resolve().parents[1] / "api" / "main.py"
API_MAIN_SPEC = importlib.util.spec_from_file_location("chatwithdocs_api_main", API_MAIN_PATH)
assert API_MAIN_SPEC is not None
assert API_MAIN_SPEC.loader is not None
api_main = importlib.util.module_from_spec(API_MAIN_SPEC)
API_MAIN_SPEC.loader.exec_module(api_main)


class DummyChatEngine:
    """Lightweight chat engine for API contract tests."""

    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager

    async def chat(self, user_id: str, thread_id: str | None, message: str) -> dict:
        if thread_id:
            thread = self.conversation_manager.get_thread(thread_id)
            if not thread or thread.user_id != user_id:
                thread = self.conversation_manager.create_thread(user_id)
        else:
            thread = self.conversation_manager.create_thread(user_id)

        self.conversation_manager.add_user_message(thread.id, message)
        reply = f"Echo: {message}"
        self.conversation_manager.add_assistant_message(thread.id, reply, citations=[])

        return {
            "thread_id": thread.id,
            "content": reply,
            "citations": [],
            "sources": [],
        }

    async def get_thread_history(self, thread_id: str, user_id: str) -> dict | None:
        thread = self.conversation_manager.get_thread(thread_id)
        if not thread or thread.user_id != user_id:
            return None

        return {
            "id": thread.id,
            "title": thread.title,
            "created_at": thread.created_at.isoformat(),
            "updated_at": thread.updated_at.isoformat(),
            "messages": [message.to_dict() for message in thread.messages],
        }


class DummyIngestionPipeline:
    """Simulates sandboxing by moving the uploaded temp file away."""

    def __init__(self):
        self._storage_dir = Path(tempfile.mkdtemp())

    async def ingest_file(self, file_path: Path, user_id: str) -> dict:
        moved_path = self._storage_dir / f"{user_id}_{file_path.name}"
        shutil.move(str(file_path), str(moved_path))
        return {
            "success": True,
            "file_path": str(moved_path),
            "chunks_indexed": 1,
            "error": None,
        }

    def cleanup(self) -> None:
        shutil.rmtree(self._storage_dir, ignore_errors=True)


@pytest.fixture
def api_client(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        persistence = ChatPersistence(Path(tmpdir) / "chat.db")
        conversation_manager = ConversationManager(persistence)
        chat_engine = DummyChatEngine(conversation_manager)
        ingestion_pipeline = DummyIngestionPipeline()

        monkeypatch.setattr(api_main, "conversation_manager", conversation_manager)
        monkeypatch.setattr(api_main, "chat_engine", chat_engine)
        monkeypatch.setattr(api_main, "ingestion_pipeline", ingestion_pipeline)
        monkeypatch.setattr(
            api_main,
            "injection_detector",
            PromptInjectionDetector(enabled=False),
        )

        client = TestClient(api_main.app)
        try:
            yield client, conversation_manager
        finally:
            client.close()
            ingestion_pipeline.cleanup()


class TestApiAuthBoundary:
    def test_chat_requires_user_header(self, api_client):
        client, _ = api_client

        response = client.post("/api/chat", json={"message": "hello"})

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing X-User-Id header"

    def test_upload_requires_user_header(self, api_client):
        client, _ = api_client

        response = client.post(
            "/api/upload",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )

        assert response.status_code == 401
        assert response.json()["detail"] == "Missing X-User-Id header"

    def test_conversation_routes_require_user_header(self, api_client):
        client, _ = api_client

        list_response = client.get("/api/conversations")
        get_response = client.get("/api/conversations/thread-123")
        delete_response = client.delete("/api/conversations/thread-123")

        assert list_response.status_code == 401
        assert get_response.status_code == 401
        assert delete_response.status_code == 401

    def test_blank_user_header_is_rejected(self, api_client):
        client, _ = api_client

        response = client.get("/api/conversations", headers={"X-User-Id": "   "})

        assert response.status_code == 400
        assert response.json()["detail"] == "X-User-Id header must not be blank"


class TestApiConversationOwnership:
    def test_chat_creation_and_followup_use_header_identity(self, api_client):
        client, _ = api_client
        headers = {"X-User-Id": "alice"}

        first = client.post("/api/chat", headers=headers, json={"message": "hello"})
        assert first.status_code == 200
        first_thread_id = first.json()["thread_id"]

        second = client.post(
            "/api/chat",
            headers=headers,
            json={"message": "follow up", "thread_id": first_thread_id},
        )
        assert second.status_code == 200
        assert second.json()["thread_id"] == first_thread_id

        conversations = client.get("/api/conversations", headers=headers)
        assert conversations.status_code == 200
        payload = conversations.json()["conversations"]
        assert len(payload) == 1
        assert payload[0]["id"] == first_thread_id

    def test_get_conversation_blocks_cross_user_access(self, api_client):
        client, conversation_manager = api_client
        thread = conversation_manager.create_thread("alice", title="Private")

        response = client.get(
            f"/api/conversations/{thread.id}",
            headers={"X-User-Id": "bob"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Conversation not found"

    def test_delete_conversation_blocks_cross_user_access(self, api_client):
        client, conversation_manager = api_client
        thread = conversation_manager.create_thread("alice", title="Private")

        response = client.delete(
            f"/api/conversations/{thread.id}",
            headers={"X-User-Id": "bob"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Conversation not found"

        owner_view = client.get("/api/conversations", headers={"X-User-Id": "alice"})
        assert owner_view.status_code == 200
        assert len(owner_view.json()["conversations"]) == 1


class TestApiUploads:
    def test_upload_succeeds_when_ingestion_moves_temp_file(self, api_client):
        client, _ = api_client

        response = client.post(
            "/api/upload",
            headers={"X-User-Id": "alice"},
            files={"file": ("notes.txt", b"hello world", "text/plain")},
        )

        assert response.status_code == 200
        assert response.json()["success"] is True
        assert response.json()["chunks_indexed"] == 1

    def test_upload_rejects_unsupported_extension(self, api_client):
        client, _ = api_client

        response = client.post(
            "/api/upload",
            headers={"X-User-Id": "alice"},
            files={"file": ("payload.exe", b"boom", "application/octet-stream")},
        )

        assert response.status_code == 400
        assert "File type not allowed" in response.json()["detail"]
