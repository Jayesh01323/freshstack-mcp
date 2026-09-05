"""Unit tests for SQLite evidence and metadata caching."""

import time
from pathlib import Path
import pytest
from freshstack.cache import SQLiteCache
from freshstack.models import EvidenceSource, SourceType


def test_sqlite_cache_evidence(tmp_path: Path):
    db_path = tmp_path / "test_freshstack.db"
    test_cache = SQLiteCache(db_path=db_path)

    ev = EvidenceSource(
        source_type=SourceType.OFFICIAL_DOC,
        title="FastAPI Lifespan Documentation",
        url="https://fastapi.tiangolo.com/advanced/events/#lifespan",
        details="Use lifespan parameter instead of on_event"
    )

    test_cache.set_evidence("fastapi:lifespan", ev, ttl_seconds=3600)
    retrieved = test_cache.get_evidence("fastapi:lifespan")

    assert retrieved is not None
    assert retrieved.title == ev.title
    assert retrieved.url == ev.url
    assert retrieved.source_type == SourceType.OFFICIAL_DOC


def test_sqlite_cache_expiration(tmp_path: Path):
    db_path = tmp_path / "test_freshstack.db"
    test_cache = SQLiteCache(db_path=db_path)

    ev = EvidenceSource(
        source_type=SourceType.CHANGELOG,
        title="Short-lived note",
        url="https://example.com"
    )

    # Set 1 second TTL
    test_cache.set_evidence("temp:note", ev, ttl_seconds=1)
    assert test_cache.get_evidence("temp:note") is not None

    time.sleep(1.2)
    assert test_cache.get_evidence("temp:note") is None


def test_sqlite_cache_pypi_metadata(tmp_path: Path):
    db_path = tmp_path / "test_freshstack.db"
    test_cache = SQLiteCache(db_path=db_path)

    data = {
        "name": "fastapi",
        "latest_version": "0.115.0",
        "versions": ["0.114.0", "0.115.0"]
    }

    test_cache.set_pypi_metadata("FastAPI", data, latest_version="0.115.0", ttl_seconds=3600)
    retrieved = test_cache.get_pypi_metadata("fastapi")

    assert retrieved is not None
    assert retrieved["latest_version"] == "0.115.0"
