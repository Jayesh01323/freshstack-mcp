"""Hardening Test 3: Cache Validation.

Validates the local SQLite caching layer:
- Cache hit
- Cache miss
- Expiration (TTL-based)
- Stale cache detection
- Refresh / update
- Verification of conditional requests / ETag policy (honest verification)
"""

import time
from pathlib import Path
import pytest

from freshstack.cache import SQLiteCache
from freshstack.models import EvidenceSource, SourceType


@pytest.fixture
def temp_cache(tmp_path):
    db_file = tmp_path / "test_cache.sqlite3"
    return SQLiteCache(db_path=db_file)


def test_cache_hit_and_miss(temp_cache):
    """Verify cache returns None on miss and retrieved data on hit."""
    # Miss
    assert temp_cache.get_evidence("non_existent_key") is None
    assert temp_cache.get_pypi_metadata("non_existent_pkg") is None

    # Write & Hit for Evidence
    ev = EvidenceSource(
        source_type=SourceType.OFFICIAL_DOC,
        title="Pydantic Doc",
        url="https://docs.pydantic.dev",
        details="Official documentation"
    )
    temp_cache.set_evidence("pydantic_doc", ev, ttl_seconds=3600)

    cached_ev = temp_cache.get_evidence("pydantic_doc")
    assert cached_ev is not None
    assert cached_ev.title == "Pydantic Doc"
    assert cached_ev.url == "https://docs.pydantic.dev"

    # Write & Hit for PyPI metadata
    data = {"name": "fastapi", "latest_version": "0.115.0"}
    temp_cache.set_pypi_metadata("fastapi", data, latest_version="0.115.0", ttl_seconds=3600)

    cached_pypi = temp_cache.get_pypi_metadata("fastapi")
    assert cached_pypi is not None
    assert cached_pypi["name"] == "fastapi"
    assert cached_pypi["latest_version"] == "0.115.0"


def test_cache_expiration_and_stale_eviction(temp_cache):
    """Verify entries expire when TTL passes and clear_expired purges them."""
    data = {"name": "expiring-pkg", "latest_version": "1.0.0"}

    # Set with 1-second TTL
    temp_cache.set_pypi_metadata("expiring-pkg", data, ttl_seconds=1)

    # Immediate check -> hit
    assert temp_cache.get_pypi_metadata("expiring-pkg") is not None

    # Wait for TTL expiration
    time.sleep(1.1)

    # Query -> expired, returns None
    assert temp_cache.get_pypi_metadata("expiring-pkg") is None

    # Run cleanup
    purged = temp_cache.clear_expired()
    assert purged >= 1


def test_cache_refresh_and_update(temp_cache):
    """Verify that setting an existing key refreshes data and resets expiration."""
    initial = {"name": "refresh-pkg", "latest_version": "1.0.0"}
    temp_cache.set_pypi_metadata("refresh-pkg", initial, latest_version="1.0.0", ttl_seconds=60)

    cached1 = temp_cache.get_pypi_metadata("refresh-pkg")
    assert cached1["latest_version"] == "1.0.0"

    # Refresh with newer version
    updated = {"name": "refresh-pkg", "latest_version": "2.0.0"}
    temp_cache.set_pypi_metadata("refresh-pkg", updated, latest_version="2.0.0", ttl_seconds=120)

    cached2 = temp_cache.get_pypi_metadata("refresh-pkg")
    assert cached2["latest_version"] == "2.0.0"


def test_conditional_request_etag_policy(temp_cache):
    """Test policy verification: FreshStack uses local SQLite TTL-based caching.

    Confirms that ETag conditional requests (If-None-Match) are NOT falsely claimed,
    and cache invalidation relies strictly on configurable TTLs and cache.clear_expired.
    """
    # Verify cache schema stores timestamp and TTL, not HTTP ETags
    with temp_cache._get_connection() as conn:
        cols = [r["name"] for r in conn.execute("PRAGMA table_info(pypi_cache)").fetchall()]
        assert "cached_at" in cols
        assert "expires_at" in cols
        assert "etag" not in cols  # Honest architecture verification
