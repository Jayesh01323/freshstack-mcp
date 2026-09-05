"""Unit tests for constraint resolution pipeline."""

from pathlib import Path
import pytest
from freshstack.models import Confidence, ResolvedConstraints
from freshstack.resolve import ConstraintResolver, resolve_constraints


def test_resolve_constraints_with_uv_fixture():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    resolver = ConstraintResolver(str(fixture_dir))

    result: ResolvedConstraints = resolver.resolve(
        task_description="Build a REST API with FastAPI and Pydantic validation",
        libraries=["fastapi", "pydantic", "sqlalchemy"]
    )

    assert result.confidence == Confidence.VERIFIED
    assert result.libraries["fastapi"] == "0.115.0"
    assert result.libraries["pydantic"] == "2.9.2"
    assert result.libraries["sqlalchemy"] == "2.0.35"

    # Deprecated patterns identified
    deprecated_names = [d.name for d in result.deprecated_patterns]
    assert any("dict()" in d for d in deprecated_names)
    assert any("on_event" in d for d in deprecated_names)
    assert any("query" in d for d in deprecated_names)

    # Evidence sources attached
    assert len(result.evidence_sources) > 0
    assert any("fastapi.tiangolo.com" in (ev.url or "") for ev in result.evidence_sources)
    assert any("docs.pydantic.dev" in (ev.url or "") for ev in result.evidence_sources)


def test_resolve_constraints_unknown_library():
    result = resolve_constraints(
        task_description="Build UI with Flutter",
        libraries=["flutter_unknown_lib"]
    )

    # Unknown libraries lower confidence
    assert result.confidence == Confidence.UNKNOWN
