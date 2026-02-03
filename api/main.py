"""FastAPI server for ChatWithDocs RAG system API.

Provides REST API endpoints for:
- Chat with documents
- File upload and management
- Conversation history
- Health checks
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from chatwithdocs.chat.engine import ChatEngine
from chatwithdocs.chat.manager import ConversationManager
from chatwithdocs.config import settings
from chatwithdocs.ingestion import IngestionPipeline
from chatwithdocs.security import PromptInjectionDetector

logger = logging.getLogger(__name__)

# Global service instances
chat_engine: ChatEngine | None = None
conversation_manager: ConversationManager | None = None
ingestion_pipeline: IngestionPipeline | None = None
injection_detector: PromptInjectionDetector | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup services."""
    global chat_engine, conversation_manager, ingestion_pipeline, injection_detector

    # Initialize services on startup
    logger.info("Initializing services...")
    chat_engine = ChatEngine()
    conversation_manager = ConversationManager()
    ingestion_pipeline = IngestionPipeline()
    injection_detector = PromptInjectionDetector()
    logger.info("Services initialized")

    yield

    # Cleanup on shutdown
    logger.info("Shutting down...")


app = FastAPI(
    title="Edan-V2 RAG API",
    description="AI-powered document chat with retrieval and citations",
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models
class ChatRequest(BaseModel):
    """Chat request model."""

    message: str
    user_id: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    """Chat response model."""

    thread_id: str
    content: str
    citations: List[dict]
    sources: List[str]


class ConversationListResponse(BaseModel):
    """Conversation list response."""

    conversations: List[dict]


class UploadResponse(BaseModel):
    """File upload response."""

    success: bool
    filename: str
    chunks_indexed: int
    error: str | None = None


class ErrorResponse(BaseModel):
    """Error response model."""

    detail: str


# Health check endpoint
@app.get("/api/health", tags=["Health"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "version": settings.app_version,
        "services": {
            "chat_engine": chat_engine is not None,
            "vector_store": True,
            "ingestion": ingestion_pipeline is not None,
        },
    }


# Chat endpoint
@app.post("/api/chat", response_model=ChatResponse, tags=["Chat"])
async def chat(request: ChatRequest):
    """Send a chat message and get AI response.

    Args:
        request: Chat request with message, user_id, and optional thread_id

    Returns:
        AI response with citations from documents
    """
    if not chat_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat engine not initialized",
        )

    # Check for prompt injection
    if injection_detector and settings.enable_injection_detection:
        check = injection_detector.check(request.message)
        if not check.is_safe:
            safe_msg = injection_detector.get_safe_alternative(request.message, check.reason)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Potentially unsafe message: {safe_msg}",
            )

    try:

        response = await chat_engine.chat(
            user_id=request.user_id,
            thread_id=request.thread_id,
            message=request.message,
        )

        return ChatResponse(
            thread_id=response["thread_id"],
            content=response["content"],
            citations=response["citations"],
            sources=response["sources"],
        )

    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chat processing failed: {str(e)}",
        )


# File upload endpoint
@app.post("/api/upload", response_model=UploadResponse, tags=["Files"])
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Form(...),
):
    """Upload and index a document.

    Args:
        file: Document file to upload (PDF, DOCX, CSV, TXT, MD)
        user_id: User identifier

    Returns:
        Upload status with chunks indexed
    """
    if not ingestion_pipeline:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ingestion pipeline not initialized",
        )

    # Check file extension
    allowed_exts = settings.allowed_extensions
    file_ext = file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_exts)}",
        )

    try:
        # Save uploaded file temporarily
        import tempfile

        temp_dir = tempfile.mkdtemp()
        temp_path = Path(temp_dir) / file.filename

        content = await file.read()
        temp_path.write_bytes(content)

        # Ingest the file
        result = await ingestion_pipeline.ingest_file(temp_path, user_id)

        # Cleanup temp file
        temp_path.unlink()

        return UploadResponse(
            success=result["success"],
            filename=file.filename,
            chunks_indexed=result.get("chunks_indexed", 0),
            error=result.get("error"),
        )

    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File upload failed: {str(e)}",
        )


# List conversations endpoint
@app.get(
    "/api/conversations/{user_id}", response_model=ConversationListResponse, tags=["Conversations"]
)
async def list_conversations(user_id: str):
    """List all conversations for a user.

    Args:
        user_id: User identifier

    Returns:
        List of conversations
    """
    if not conversation_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation manager not initialized",
        )

    try:
        conversations = conversation_manager.list_conversations(user_id)
        return ConversationListResponse(conversations=conversations)
    except Exception as e:
        logger.error(f"List conversations error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list conversations: {str(e)}",
        )


# Get conversation history endpoint
@app.get("/api/conversations/{user_id}/{thread_id}", tags=["Conversations"])
async def get_conversation(user_id: str, thread_id: str):
    """Get full conversation history.

    Args:
        user_id: User identifier
        thread_id: Conversation thread ID

    Returns:
        Conversation details with messages
    """
    if not chat_engine:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Chat engine not initialized",
        )

    try:

        history = await chat_engine.get_thread_history(thread_id, user_id)

        if not history:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return history

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get conversation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation: {str(e)}",
        )


# Delete conversation endpoint
@app.delete("/api/conversations/{user_id}/{thread_id}", tags=["Conversations"])
async def delete_conversation(user_id: str, thread_id: str):
    """Delete a conversation.

    Args:
        user_id: User identifier
        thread_id: Conversation thread ID

    Returns:
        Deletion status
    """
    if not conversation_manager:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Conversation manager not initialized",
        )

    try:
        success = conversation_manager.delete_conversation(thread_id, user_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )

        return {"success": True, "message": "Conversation deleted"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete conversation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversation: {str(e)}",
        )


# Error handlers
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    """Handle generic exceptions."""
    logger.error(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
