from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from chatwithdocs.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AuditEvent:
    """A security audit event."""

    event_type: str  # "file_upload", "query", "auth", "security", etc.
    user_id: Optional[str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action: str = ""  # e.g., "upload", "download", "delete", "query"
    resource: str = ""  # e.g., file path, thread ID
    details: Dict[str, Any] = field(default_factory=dict)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    success: bool = True
    error_message: Optional[str] = None
    session_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_type": self.event_type,
            "user_id": self.user_id,
            "timestamp": self.timestamp.isoformat(),
            "action": self.action,
            "resource": self.resource,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "success": self.success,
            "error_message": self.error_message,
            "session_id": self.session_id,
        }

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), default=str)


class AuditLogger:
    """Audit logging system for security and compliance.

    Logs security-relevant events:
    - File uploads/downloads
    - User queries
    - Authentication attempts
    - Security violations
    - Data access
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self.log_dir = log_dir or (settings.data_dir / "audit_logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Daily log file rotation
        self._current_date = datetime.now(timezone.utc).date()
        self._log_file = self._get_log_file()

        # In-memory buffer for recent events (useful for real-time monitoring)
        self._recent_events: List[AuditEvent] = []
        self._max_buffer_size = 1000

    def _get_log_file(self) -> Path:
        """Get current log file path (rotates daily)."""
        date_str = self._current_date.strftime("%Y-%m-%d")
        return self.log_dir / f"audit_{date_str}.jsonl"

    def _rotate_if_needed(self):
        """Rotate log file if date changed."""
        current_date = datetime.now(timezone.utc).date()
        if current_date != self._current_date:
            self._current_date = current_date
            self._log_file = self._get_log_file()

    def log(self, event: AuditEvent) -> None:
        """Log an audit event.

        Args:
            event: Audit event to log
        """
        self._rotate_if_needed()

        # Write to file
        try:
            with open(self._log_file, "a") as f:
                f.write(event.to_json() + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

        # Add to buffer
        self._recent_events.append(event)
        if len(self._recent_events) > self._max_buffer_size:
            self._recent_events.pop(0)

        # Also log to standard logger for critical events
        if event.event_type == "security" or not event.success:
            logger.warning(
                f"Audit: {event.event_type} - {event.action} - "
                f"User: {event.user_id} - Success: {event.success}"
            )

    def log_file_upload(
        self,
        user_id: str,
        filename: str,
        file_hash: str,
        file_size: int,
        success: bool = True,
        error: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """Log a file upload event."""
        event = AuditEvent(
            event_type="file_upload",
            user_id=user_id,
            action="upload",
            resource=filename,
            details={
                "file_hash": file_hash,
                "file_size_bytes": file_size,
                "file_name": filename,
            },
            ip_address=ip_address,
            success=success,
            error_message=error,
        )
        self.log(event)

    def log_query(
        self,
        user_id: str,
        thread_id: str,
        query: str,
        success: bool = True,
        error: Optional[str] = None,
        ip_address: Optional[str] = None,
        query_hash: Optional[str] = None,
    ) -> None:
        """Log a user query."""
        # Hash the query for privacy (don't store full query text)
        if query_hash is None and query:
            import hashlib

            query_hash = hashlib.sha256(query.encode()).hexdigest()[:16]

        event = AuditEvent(
            event_type="query",
            user_id=user_id,
            action="chat_query",
            resource=thread_id,
            details={
                "query_hash": query_hash,
                "query_length": len(query) if query else 0,
            },
            ip_address=ip_address,
            success=success,
            error_message=error,
        )
        self.log(event)

    def log_security_event(
        self,
        event_type: str,  # "injection_attempt", "unauthorized_access", etc.
        user_id: Optional[str],
        details: Dict[str, Any],
        ip_address: Optional[str] = None,
        severity: str = "warning",
    ) -> None:
        """Log a security-related event."""
        event = AuditEvent(
            event_type="security",
            user_id=user_id,
            action=event_type,
            resource=details.get("resource", ""),
            details={**details, "severity": severity},
            ip_address=ip_address,
            success=False,  # Security events are failures
        )
        self.log(event)

    def log_auth(
        self,
        user_id: Optional[str],
        action: str,  # "login", "logout", "failed_login"
        success: bool,
        ip_address: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an authentication event."""
        event = AuditEvent(
            event_type="auth",
            user_id=user_id,
            action=action,
            details=details or {},
            ip_address=ip_address,
            success=success,
        )
        self.log(event)

    def log_data_access(
        self,
        user_id: str,
        resource_type: str,  # "thread", "file", "chunk"
        resource_id: str,
        action: str,  # "read", "delete", "list"
        success: bool = True,
        ip_address: Optional[str] = None,
    ) -> None:
        """Log data access events."""
        event = AuditEvent(
            event_type="data_access",
            user_id=user_id,
            action=action,
            resource=f"{resource_type}:{resource_id}",
            ip_address=ip_address,
            success=success,
        )
        self.log(event)

    def get_recent_events(
        self,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEvent]:
        """Get recent events from memory buffer.

        Args:
            event_type: Filter by event type
            user_id: Filter by user
            limit: Maximum number of events

        Returns:
            List of recent audit events
        """
        events = self._recent_events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if user_id:
            events = [e for e in events if e.user_id == user_id]

        return events[-limit:]

    def get_events_from_file(
        self,
        date: Optional[datetime] = None,
        event_type: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[AuditEvent]:
        """Read events from log file.

        Args:
            date: Date to read (default: today)
            event_type: Filter by event type
            user_id: Filter by user

        Returns:
            List of audit events
        """
        if date is None:
            date = datetime.now(timezone.utc)

        log_file = self.log_dir / f"audit_{date.strftime('%Y-%m-%d')}.jsonl"

        if not log_file.exists():
            return []

        events = []
        try:
            with open(log_file, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        event = AuditEvent(
                            event_type=data["event_type"],
                            user_id=data.get("user_id"),
                            timestamp=datetime.fromisoformat(data["timestamp"]),
                            action=data.get("action", ""),
                            resource=data.get("resource", ""),
                            details=data.get("details", {}),
                            ip_address=data.get("ip_address"),
                            user_agent=data.get("user_agent"),
                            success=data.get("success", True),
                            error_message=data.get("error_message"),
                            session_id=data.get("session_id"),
                        )

                        # Apply filters
                        if event_type and event.event_type != event_type:
                            continue
                        if user_id and event.user_id != user_id:
                            continue

                        events.append(event)
                    except (json.JSONDecodeError, KeyError) as e:
                        logger.error(f"Failed to parse audit log line: {e}")
                        continue
        except Exception as e:
            logger.error(f"Failed to read audit log file: {e}")

        return events

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete audit logs older than N days.

        Args:
            days: Age in days

        Returns:
            Number of files deleted
        """
        from datetime import timedelta

        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        deleted = 0

        for log_file in self.log_dir.glob("audit_*.jsonl"):
            try:
                # Extract date from filename
                date_str = log_file.stem.replace("audit_", "")
                file_date = datetime.strptime(date_str, "%Y-%m-%d")
                file_date = file_date.replace(tzinfo=timezone.utc)

                if file_date < cutoff:
                    log_file.unlink()
                    deleted += 1
                    logger.debug(f"Deleted old audit log: {log_file.name}")
            except Exception as e:
                logger.error(f"Failed to clean up {log_file}: {e}")

        logger.info(f"Audit log cleanup complete: {deleted} files deleted")
        return deleted


# Global audit logger instance
audit_logger = AuditLogger()
