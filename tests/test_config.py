from __future__ import annotations

from pathlib import Path

from chatwithdocs.config import Settings, settings


class TestSettings:
    """Test suite for configuration settings."""

    def test_default_settings(self):
        """Test that default settings are properly initialized."""
        assert settings.app_name == "chatwithdocs"
        assert settings.app_version == "2.0.0"
        assert settings.debug is False

    def test_embedding_provider_default(self):
        """Test default embedding provider."""
        assert settings.embedding_provider.value == "auto"

    def test_local_embedding_model(self):
        """Test local embedding model configuration."""
        assert settings.local_embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
        assert settings.local_embedding_device == "cpu"

    def test_vector_store_default(self):
        """Test default vector store."""
        assert settings.vector_store.value == "chroma"

    def test_file_upload_limits(self):
        """Test file upload configuration."""
        assert settings.max_file_size_mb == 50
        assert "pdf" in settings.allowed_extensions
        assert "docx" in settings.allowed_extensions

    def test_security_defaults(self):
        """Test security configuration defaults."""
        assert settings.enable_auth is True
        assert settings.enable_file_sandbox is True
        assert settings.enable_injection_detection is True

    def test_chroma_path(self):
        """Test ChromaDB path generation."""
        path = settings.get_chroma_path()
        assert isinstance(path, Path)
        assert "chroma" in str(path)


class TestSettingsCustomValues:
    """Test custom settings values."""

    def test_custom_embedding_provider(self):
        """Test setting custom embedding provider."""
        from chatwithdocs.config.settings import EmbeddingProvider

        custom_settings = Settings(embedding_provider=EmbeddingProvider.LOCAL)
        assert custom_settings.embedding_provider == EmbeddingProvider.LOCAL

    def test_path_validation(self):
        """Test path validation and creation."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            custom_settings = Settings(
                data_dir=Path(tmpdir) / "data", upload_dir=Path(tmpdir) / "uploads"
            )
            # Directories should be created automatically
            assert custom_settings.upload_dir.exists()
