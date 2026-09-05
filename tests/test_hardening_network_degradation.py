"""Hardening Test 2: Network Failure & Graceful Degradation.

Tests the evidence and registry layers under various network failure modes:
- PyPI timeout
- Official documentation timeout
- HTTP 5xx
- Malformed response
- Temporary network failure
- Unavailable registry

Verifies:
- Cached valid evidence is reused when network fails
- Failures are explicitly represented in EvidenceSource
- Confidence is downgraded appropriately (e.g. VERIFIED -> INFERRED or UNKNOWN)
- FreshStack never invents evidence or constraints
- UNKNOWN is returned when evidence is insufficient
"""

import json
from unittest.mock import MagicMock, patch
import httpx
import pytest

from freshstack.cache import cache
from freshstack.models import Confidence, SourceType
from freshstack.pypi import PyPIClient
from freshstack.resolve import ConstraintResolver


@pytest.fixture
def mock_pypi():
    client = PyPIClient(timeout=1.0)
    return client


def test_pypi_timeout_degradation(mock_pypi):
    """Test behavior when PyPI network requests time out."""
    with patch("httpx.Client.get", side_effect=httpx.TimeoutException("Connection timed out")):
        res = mock_pypi.get_package_info("test-timeout-pkg")
        assert res is None
        assert "test-timeout-pkg" in mock_pypi.last_errors
        assert "timeout" in mock_pypi.last_errors["test-timeout-pkg"].lower()

        # Evidence should explicitly represent the unavailable registry
        ev = mock_pypi.get_evidence_source("test-timeout-pkg", "1.0.0")
        assert ev.source_type == SourceType.PYPI_REGISTRY
        assert "Unavailable" in ev.title
        assert "timeout" in ev.details.lower()


def test_pypi_http_5xx_server_error(mock_pypi):
    """Test behavior when PyPI returns HTTP 500/503 server error."""
    mock_resp = MagicMock()
    mock_resp.status_code = 503

    with patch("httpx.Client.get", return_value=mock_resp):
        res = mock_pypi.get_package_info("test-503-pkg")
        assert res is None
        assert "test-503-pkg" in mock_pypi.last_errors
        assert "503" in mock_pypi.last_errors["test-503-pkg"]

        ev = mock_pypi.get_evidence_source("test-503-pkg")
        assert "Unavailable" in ev.title
        assert "503" in ev.details


def test_pypi_malformed_response(mock_pypi):
    """Test behavior when PyPI returns malformed / non-JSON content."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = json.JSONDecodeError("Expecting value", "doc", 0)

    with patch("httpx.Client.get", return_value=mock_resp):
        res = mock_pypi.get_package_info("test-malformed-pkg")
        assert res is None
        assert "Malformed JSON" in mock_pypi.last_errors.get("test-malformed-pkg", "")


def test_cached_evidence_reused_during_network_outage(mock_pypi):
    """Test that valid cached metadata is reused seamlessly during a complete network outage."""
    pkg_name = "test-cached-outage-pkg"
    cached_data = {
        "name": pkg_name,
        "latest_version": "3.5.0",
        "requires_python": ">=3.10",
        "summary": "Cached package for outage test",
        "versions": ["3.4.0", "3.5.0"],
        "fetched_at": "2026-09-05T00:00:00Z"
    }
    cache.set_pypi_metadata(pkg_name, cached_data, latest_version="3.5.0")

    # Network completely broken
    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Network unreachable")):
        res = mock_pypi.get_package_info(pkg_name)
        assert res is not None
        assert res["latest_version"] == "3.5.0"

        # Evidence source is generated from verified cache
        ev = mock_pypi.get_evidence_source(pkg_name, "3.5.0")
        assert "Unavailable" not in ev.title
        assert "cached latest: 3.5.0" in ev.details


def test_confidence_downgrade_and_no_hallucination():
    """Verify that when registry verification fails and local evidence is degraded:

    - Confidence is downgraded from VERIFIED to INFERRED or UNKNOWN
    - Unsupported packages produce UNKNOWN confidence with zero invented constraints
    """
    resolver = ConstraintResolver(project_dir=".")

    # 1. Unsupported package with network failure
    with patch("freshstack.pypi.pypi_client.get_package_info", return_value=None):
        result = resolver.resolve(
            task_description="Testing unknown package",
            libraries=["completely_fictional_unsupported_lib"]
        )

        assert result.confidence == Confidence.UNKNOWN
        assert len(result.deprecated_patterns) == 0
        assert len(result.version_specific_apis) == 0
        # Check evidence reports unsupported library explicitly
        unsupported_ev = [e for e in result.evidence_sources if "Unsupported" in e.title]
        assert len(unsupported_ev) == 1

    # 2. Known library with network degradation during resolve
    with patch.object(PyPIClient, "get_package_info", return_value=None):
        with patch.dict("freshstack.pypi.pypi_client.last_errors", {"pydantic": "PyPI timeout"}):
            # Target pydantic with pinned version but degraded PyPI
            res_degraded = resolver.resolve(
                task_description="Build schema",
                libraries={"pydantic": "2.9.2"}
            )
            # Pydantic is supported and version is specified, but PyPI is degraded -> INFERRED
            assert res_degraded.confidence == Confidence.INFERRED
            titles = [e.title for e in res_degraded.evidence_sources]
            assert any("Unavailable" in t for t in titles)
