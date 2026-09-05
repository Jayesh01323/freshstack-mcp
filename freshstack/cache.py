"""Local SQLite evidence and constraint cache for FreshStack MCP."""

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, Optional

from freshstack.config import config, logger
from freshstack.models import EvidenceSource, SourceType


class SQLiteCache:
    """Thread-safe SQLite caching layer for authoritative evidence and package metadata."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or config.db_path
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Create cache tables if they do not exist."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS evidence_cache (
                        cache_key TEXT PRIMARY KEY,
                        source_type TEXT NOT NULL,
                        title TEXT NOT NULL,
                        url TEXT,
                        details TEXT,
                        verified_at TEXT NOT NULL,
                        expires_at INTEGER NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS pypi_cache (
                        package_name TEXT PRIMARY KEY,
                        data_json TEXT NOT NULL,
                        latest_version TEXT,
                        cached_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS audit_cache (
                        code_hash TEXT PRIMARY KEY,
                        report_json TEXT NOT NULL,
                        cached_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_evidence_expires ON evidence_cache(expires_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_pypi_expires ON pypi_cache(expires_at)")
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize SQLite cache database: {e}")

    def get_evidence(self, cache_key: str) -> Optional[EvidenceSource]:
        """Retrieve cached evidence if present and not expired."""
        now = int(time.time())
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT source_type, title, url, details, verified_at FROM evidence_cache WHERE cache_key = ? AND (expires_at = 0 OR expires_at > ?)",
                    (cache_key, now)
                ).fetchone()
                if row:
                    return EvidenceSource(
                        source_type=SourceType(row["source_type"]),
                        title=row["title"],
                        url=row["url"],
                        details=row["details"],
                        verified_at=row["verified_at"]
                    )
        except Exception as e:
            logger.warning(f"Error reading evidence cache for key '{cache_key}': {e}")
        return None

    def set_evidence(self, cache_key: str, evidence: EvidenceSource, ttl_seconds: int = 86400) -> None:
        """Store evidence in cache with specified TTL (default 24 hours, 0 for permanent)."""
        now = int(time.time())
        expires_at = now + ttl_seconds if ttl_seconds > 0 else 0
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO evidence_cache
                    (cache_key, source_type, title, url, details, verified_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    cache_key,
                    evidence.source_type.value,
                    evidence.title,
                    evidence.url,
                    evidence.details,
                    evidence.verified_at,
                    expires_at
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error writing evidence cache for key '{cache_key}': {e}")

    def get_pypi_metadata(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached PyPI registry metadata for a package."""
        normalized_name = package_name.lower().replace("_", "-")
        now = int(time.time())
        try:
            with self._get_connection() as conn:
                row = conn.execute(
                    "SELECT data_json FROM pypi_cache WHERE package_name = ? AND (expires_at = 0 OR expires_at > ?)",
                    (normalized_name, now)
                ).fetchone()
                if row:
                    return json.loads(row["data_json"])
        except Exception as e:
            logger.warning(f"Error reading PyPI cache for '{package_name}': {e}")
        return None

    def set_pypi_metadata(
        self,
        package_name: str,
        data: Dict[str, Any],
        latest_version: Optional[str] = None,
        ttl_seconds: int = 43200
    ) -> None:
        """Store PyPI metadata with TTL (default 12 hours)."""
        normalized_name = package_name.lower().replace("_", "-")
        now = int(time.time())
        expires_at = now + ttl_seconds if ttl_seconds > 0 else 0
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO pypi_cache
                    (package_name, data_json, latest_version, cached_at, expires_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    normalized_name,
                    json.dumps(data),
                    latest_version,
                    now,
                    expires_at
                ))
                conn.commit()
        except Exception as e:
            logger.warning(f"Error writing PyPI cache for '{package_name}': {e}")

    def clear_expired(self) -> int:
        """Remove all expired cache entries. Returns count of deleted entries."""
        now = int(time.time())
        count = 0
        try:
            with self._get_connection() as conn:
                c1 = conn.execute("DELETE FROM evidence_cache WHERE expires_at > 0 AND expires_at <= ?", (now,)).rowcount
                c2 = conn.execute("DELETE FROM pypi_cache WHERE expires_at > 0 AND expires_at <= ?", (now,)).rowcount
                c3 = conn.execute("DELETE FROM audit_cache WHERE expires_at > 0 AND expires_at <= ?", (now,)).rowcount
                conn.commit()
                count = c1 + c2 + c3
        except Exception as e:
            logger.warning(f"Error clearing expired cache entries: {e}")
        return count


# Singleton cache instance
cache = SQLiteCache()
