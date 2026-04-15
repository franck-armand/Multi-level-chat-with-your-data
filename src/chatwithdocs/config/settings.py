from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmbeddingProvider(str, Enum):
    """Available embedding providers."""

    LOCAL = "local"
    OPENAI = "openai"
    AUTO = "auto"


class VectorStore(str, Enum):
    """Available vector store backends."""

    CHROMA = "chroma"


class LogLevel(str, Enum):
    """Log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Settings(BaseSettings):
    """Application settings with environment variable support.

    Priority: env vars > .env file > default values
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = Field(default="chatwithdocs", description="Application name")
    app_version: str = Field(default="2.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")
    log_level: LogLevel = Field(default=LogLevel.INFO, description="Logging level")

    # Data directories
    data_dir: Path = Field(default=Path("./data"), description="Base directory for data storage")
    upload_dir: Path = Field(
        default=Path("./data/uploads"), description="Directory for uploaded files"
    )
    vector_store_dir: Path = Field(
        default=Path("./data/vectors"),
        description="Directory for vector store persistence",
    )
    chat_history_db: Path = Field(
        default=Path("./data/chat_history.db"),
        description="SQLite database path for chat history",
    )

    # Embedding configuration
    embedding_provider: EmbeddingProvider = Field(
        default=EmbeddingProvider.AUTO,
        description="Embedding provider: local, openai, or auto",
    )
    local_embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="Local embedding model name",
    )
    local_embedding_device: str = Field(
        default="cpu", description="Device for local embeddings: cpu or cuda"
    )
    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="OpenAI embedding model name",
    )
    embedding_dimensions: int = Field(
        default=384, description="Embedding dimensions (depends on model)"
    )

    # Vector store configuration
    vector_store: VectorStore = Field(
        default=VectorStore.CHROMA, description="Vector store backend"
    )
    vector_search_top_k: int = Field(
        default=10, description="Number of results to retrieve from vector search"
    )

    # LLM configuration (for response generation)
    llm_provider: str = Field(
        default="local", description="LLM provider: local, openai, deepseek, kimi, ollama"
    )
    openai_api_key: str | None = Field(default=None, description="OpenAI API key")
    openai_base_url: str | None = Field(default=None, description="OpenAI-compatible base URL")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model for chat")

    # Kimi (Moonshot AI) configuration
    kimi_api_key: str | None = Field(default=None, description="Kimi API key")
    kimi_base_url: str = Field(
        default="https://api.moonshot.cn/v1", description="Kimi API base URL"
    )
    kimi_model: str = Field(default="kimi-k2.5", description="Kimi model name")

    # Ollama (local LLM) configuration
    ollama_base_url: str = Field(default="http://localhost:11434", description="Ollama server URL")
    ollama_model: str = Field(
        default="llama3.2", description="Ollama model name (e.g., llama3.2, mistral, qwen2.5)"
    )

    # Retrieval configuration
    use_bm25: bool = Field(default=True, description="Use BM25 keyword search in hybrid retrieval")
    use_vector_search: bool = Field(default=True, description="Use vector semantic search")
    hybrid_search_weight: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Weight for vector search in hybrid (0=BM25 only, 1=vector only)",
    )
    rerank_results: bool = Field(
        default=True, description="Rerank retrieval results with cross-encoder"
    )
    rerank_top_k: int = Field(default=5, description="Number of results after reranking")

    # Chat configuration
    max_chat_history: int = Field(default=50, description="Maximum messages per chat thread")
    context_window_tokens: int = Field(
        default=4000, description="Maximum tokens for context window"
    )
    enable_chat_tracing: bool = Field(
        default=True,
        description="Write chat retrieval/answerability traces to JSONL",
    )
    chat_trace_file: Path = Field(
        default=Path("./logs/chat_traces.jsonl"),
        description="Path for chat trace JSONL output",
    )

    # File upload configuration
    max_file_size_mb: int = Field(default=50, description="Maximum file upload size in MB")
    allowed_extensions: List[str] = Field(
        default=["pdf", "docx", "doc", "csv", "xlsx", "xls", "txt", "md"],
        description="Allowed file extensions",
    )
    auto_index_new_files: bool = Field(
        default=True, description="Automatically index new files on upload"
    )

    # Security configuration
    secret_key: str = Field(
        default="change-me-in-production",
        description="Secret key for JWT signing",
    )
    access_token_expire_minutes: int = Field(
        default=60, description="Access token expiration in minutes"
    )
    enable_auth: bool = Field(default=True, description="Enable user authentication")
    enable_file_sandbox: bool = Field(
        default=True, description="Enable file sandboxing for uploads"
    )
    enable_injection_detection: bool = Field(
        default=True, description="Enable prompt injection detection"
    )
    enable_pii_filter: bool = Field(default=True, description="Enable PII detection and redaction")

    # Chunking configuration
    chunk_size: int = Field(default=1000, description="Maximum chunk size in characters")
    chunk_overlap: int = Field(default=200, description="Overlap between chunks in characters")

    @field_validator("data_dir", "upload_dir", "vector_store_dir", "chat_trace_file", mode="before")
    @classmethod
    def ensure_path(cls, v: Any) -> Path:
        """Ensure path is a Path object."""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("upload_dir", "vector_store_dir")
    @classmethod
    def create_directories(cls, v: Path) -> Path:
        """Ensure directories exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v

    def get_chroma_path(self) -> Path:
        """Get ChromaDB persistence path."""
        return self.vector_store_dir / "chroma"


# Global settings instance
settings = Settings()
