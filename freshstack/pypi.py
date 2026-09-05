"""PyPI registry metadata client with local SQLite caching."""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import httpx
from packaging.version import Version, InvalidVersion

from freshstack.cache import cache
from freshstack.config import config, logger
from freshstack.models import EvidenceSource, SourceType


class PyPIClient:
    """Retrieves authoritative package metadata from the official PyPI JSON API."""

    BASE_URL = "https://pypi.org/pypi"

    def __init__(self, timeout: float = 8.0):
        self.timeout = timeout
        self.last_errors: Dict[str, str] = {}

    def get_package_info(self, package_name: str) -> Optional[Dict[str, Any]]:
        """Fetch package metadata from PyPI, using cache when available."""
        normalized = package_name.lower().replace("_", "-")

        # 1. Check local cache first
        cached = cache.get_pypi_metadata(normalized)
        if cached:
            logger.debug(f"PyPI cache hit for '{normalized}'")
            return cached

        if config.offline_mode:
            logger.info(f"Offline mode active: skipping network fetch for '{normalized}'")
            self.last_errors[normalized] = "Offline mode active"
            return None

        # 2. Fetch from PyPI
        url = f"{self.BASE_URL}/{normalized}/json"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url, headers={"User-Agent": "FreshStack-MCP/0.1.0"})
                if response.status_code == 404:
                    msg = f"Package '{normalized}' not found on PyPI (HTTP 404)"
                    logger.warning(msg)
                    self.last_errors[normalized] = msg
                    return None
                if response.status_code >= 500:
                    msg = f"PyPI registry server error (HTTP {response.status_code})"
                    logger.warning(msg)
                    self.last_errors[normalized] = msg
                    return None

                response.raise_for_status()

                try:
                    data = response.json()
                except Exception:
                    msg = f"Malformed JSON response received from PyPI for '{normalized}'"
                    logger.warning(msg)
                    self.last_errors[normalized] = msg
                    return None

                info = data.get("info", {})
                releases = data.get("releases", {})

                # Extract valid sorted versions
                valid_versions = []
                for v_str in releases.keys():
                    try:
                        valid_versions.append(Version(v_str))
                    except InvalidVersion:
                        continue
                valid_versions.sort()

                result = {
                    "name": info.get("name", normalized),
                    "latest_version": info.get("version"),
                    "requires_python": info.get("requires_python"),
                    "summary": info.get("summary"),
                    "project_urls": info.get("project_urls") or {},
                    "versions": [str(v) for v in valid_versions],
                    "homepage": info.get("home_page") or (info.get("project_urls") or {}).get("Homepage"),
                    "docs_url": (info.get("project_urls") or {}).get("Documentation"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                }

                # Store in SQLite cache
                cache.set_pypi_metadata(normalized, result, latest_version=result["latest_version"])
                self.last_errors.pop(normalized, None)
                return result

        except httpx.TimeoutException:
            msg = f"Timeout fetching PyPI metadata for '{normalized}' after {self.timeout}s"
            logger.warning(msg)
            self.last_errors[normalized] = msg
            return None
        except (httpx.NetworkError, httpx.ConnectError) as e:
            msg = f"Network failure connecting to PyPI for '{normalized}': {e}"
            logger.warning(msg)
            self.last_errors[normalized] = msg
            return None
        except Exception as e:
            msg = f"Failed to fetch PyPI metadata for '{normalized}': {e}"
            logger.warning(msg)
            self.last_errors[normalized] = msg
            return None

    def get_evidence_source(self, package_name: str, version: Optional[str] = None) -> EvidenceSource:
        """Construct an authoritative EvidenceSource for PyPI metadata."""
        normalized = package_name.lower().replace("_", "-")
        target_v = f"=={version}" if version else ""

        # Check local cache or attempt retrieval
        cached = cache.get_pypi_metadata(normalized)
        if cached:
            latest = cached.get("latest_version")
            return EvidenceSource(
                source_type=SourceType.PYPI_REGISTRY,
                title=f"PyPI Package Registry: {normalized}{target_v}",
                url=f"https://pypi.org/project/{normalized}/",
                details=f"Official registry metadata verified from PyPI for {normalized} (cached latest: {latest})"
            )

        # Check if an error occurred during fetch
        err = self.last_errors.get(normalized)
        if err:
            return EvidenceSource(
                source_type=SourceType.PYPI_REGISTRY,
                title=f"PyPI Registry Unavailable: {normalized}",
                url=f"https://pypi.org/project/{normalized}/",
                details=f"Registry verification degraded: {err}"
            )

        return EvidenceSource(
            source_type=SourceType.PYPI_REGISTRY,
            title=f"PyPI Package Registry: {normalized}{target_v}",
            url=f"https://pypi.org/project/{normalized}/",
            details=f"Official registry metadata verified from PyPI for {normalized}"
        )


pypi_client = PyPIClient()
