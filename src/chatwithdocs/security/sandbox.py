from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result of sandbox file processing."""

    is_safe: bool
    sanitized_path: Optional[Path] = None
    original_hash: Optional[str] = None
    error_message: Optional[str] = None
    quarantine_path: Optional[Path] = None


class FileSandbox:
    """Secure file sandbox for handling untrusted uploads.

    Features:
    - Quarantine zone for incoming files
    - File hash verification
    - Optional virus scanning (if ClamAV available)
    - Secure temporary storage
    - Automatic cleanup
    """

    def __init__(
        self,
        upload_dir: Optional[Path] = None,
        quarantine_dir: Optional[Path] = None,
        enable_virus_scan: bool = False,
    ):
        self.upload_dir = upload_dir or settings.upload_dir
        self.quarantine_dir = quarantine_dir or (self.upload_dir / "quarantine")
        self.enable_virus_scan = enable_virus_scan and settings.enable_file_sandbox

        # Create directories
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.quarantine_dir.mkdir(parents=True, exist_ok=True)

        # Check if ClamAV is available
        self._clamav_available = self._check_clamav()

    def _check_clamav(self) -> bool:
        """Check if ClamAV is installed."""
        try:
            subprocess.run(
                ["clamdscan", "--version"],
                capture_output=True,
                timeout=5,
                check=True,
            )
            logger.info("ClamAV found - virus scanning enabled")
            return True
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.debug("ClamAV not available - virus scanning disabled")
            return False

    def process_file(self, file_path: Path, user_id: str) -> SandboxResult:
        """Process an uploaded file through security checks.

        Args:
            file_path: Path to uploaded file
            user_id: User who uploaded the file

        Returns:
            SandboxResult with processing outcome
        """
        if not file_path.exists():
            return SandboxResult(
                is_safe=False,
                error_message=f"File not found: {file_path}",
            )

        try:
            # Calculate file hash
            file_hash = self._calculate_hash(file_path)

            # Move to quarantine first
            quarantine_path = self._quarantine_file(file_path, user_id, file_hash)

            # Check file size
            file_size = quarantine_path.stat().st_size
            max_size = settings.max_file_size_mb * 1024 * 1024
            if file_size > max_size:
                return SandboxResult(
                    is_safe=False,
                    error_message=f"File too large: {file_size / 1024 / 1024:.1f}MB "
                    f"(max: {settings.max_file_size_mb}MB)",
                    quarantine_path=quarantine_path,
                )

            # Virus scan if enabled
            if self.enable_virus_scan and self._clamav_available:
                scan_result = self._virus_scan(quarantine_path)
                if not scan_result:
                    return SandboxResult(
                        is_safe=False,
                        error_message="Virus scan detected threats",
                        quarantine_path=quarantine_path,
                    )

            # Move to sanitized location
            sanitized_path = self._move_to_sanitized(quarantine_path, user_id, file_hash)

            logger.info(
                f"File processed successfully: {file_path.name} (hash: {file_hash[:16]}...)"
            )

            return SandboxResult(
                is_safe=True,
                sanitized_path=sanitized_path,
                original_hash=file_hash,
            )

        except Exception as e:
            logger.error(f"Sandbox processing failed: {e}")
            return SandboxResult(
                is_safe=False,
                error_message=f"Processing failed: {str(e)}",
            )

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def _quarantine_file(self, file_path: Path, user_id: str, file_hash: str) -> Path:
        """Move file to quarantine zone."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        quarantine_name = f"{user_id}_{timestamp}_{file_hash[:16]}_{file_path.name}"
        quarantine_path = self.quarantine_dir / quarantine_name

        shutil.move(str(file_path), str(quarantine_path))
        logger.debug(f"File quarantined: {quarantine_path}")

        return quarantine_path

    def _virus_scan(self, file_path: Path) -> bool:
        """Scan file with ClamAV.

        Returns:
            True if clean, False if infected
        """
        try:
            result = subprocess.run(
                ["clamdscan", "--no-summary", str(file_path)],
                capture_output=True,
                timeout=60,
            )

            if result.returncode == 0:
                logger.debug(f"Virus scan clean: {file_path.name}")
                return True
            else:
                logger.warning(f"Virus scan found threats in: {file_path.name}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"Virus scan timeout: {file_path.name}")
            return False
        except Exception as e:
            logger.error(f"Virus scan error: {e}")
            # Fail safe - reject if scan fails
            return False

    def _move_to_sanitized(self, quarantine_path: Path, user_id: str, file_hash: str) -> Path:
        """Move file from quarantine to sanitized storage."""
        user_dir = self.upload_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)

        # Create safe filename
        original_name = quarantine_path.name.split("_")[-1]
        safe_name = f"{file_hash[:16]}_{original_name}"
        sanitized_path = user_dir / safe_name

        # Handle duplicates
        counter = 1
        while sanitized_path.exists():
            sanitized_path = user_dir / f"{file_hash[:16]}_{counter}_{original_name}"
            counter += 1

        shutil.move(str(quarantine_path), str(sanitized_path))
        logger.debug(f"File moved to sanitized storage: {sanitized_path}")

        return sanitized_path

    def cleanup_quarantine(self, max_age_hours: int = 24) -> int:
        """Clean up old quarantined files.

        Args:
            max_age_hours: Maximum age in hours

        Returns:
            Number of files cleaned up
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        cleaned = 0

        for file_path in self.quarantine_dir.iterdir():
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

                    if mtime < cutoff:
                        file_path.unlink()
                        cleaned += 1
                        logger.debug(f"Cleaned up old quarantine file: {file_path.name}")
                except Exception as e:
                    logger.error(f"Failed to clean up {file_path}: {e}")

        logger.info(f"Quarantine cleanup complete: {cleaned} files removed")
        return cleaned

    def delete_user_files(self, user_id: str) -> int:
        """Delete all files for a user.

        Args:
            user_id: User identifier

        Returns:
            Number of files deleted
        """
        user_dir = self.upload_dir / user_id
        if not user_dir.exists():
            return 0

        deleted = 0
        try:
            for file_path in user_dir.iterdir():
                if file_path.is_file():
                    file_path.unlink()
                    deleted += 1
            user_dir.rmdir()  # Remove empty directory
            logger.info(f"Deleted {deleted} files for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to delete user files: {e}")

        return deleted


class SecureTempFile:
    """Context manager for secure temporary files."""

    def __init__(self, suffix: Optional[str] = None, prefix: str = "edan_"):
        self.suffix = suffix
        self.prefix = prefix
        self.temp_path: Optional[Path] = None

    def __enter__(self) -> Path:
        """Create temporary file and return path."""

        fd, path = tempfile.mkstemp(suffix=self.suffix, prefix=self.prefix)
        os.close(fd)
        self.temp_path = Path(path)
        return self.temp_path

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Securely delete temporary file."""
        if self.temp_path and self.temp_path.exists():
            try:
                # Overwrite with zeros before deletion
                with open(self.temp_path, "wb") as f:
                    f.write(b"\x00" * self.temp_path.stat().st_size)
                self.temp_path.unlink()
            except Exception as e:
                logger.error(f"Failed to securely delete temp file: {e}")
