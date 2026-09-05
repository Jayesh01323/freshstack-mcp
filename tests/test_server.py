"""Unit tests for MCP server tool endpoints."""

import json
from pathlib import Path
import pytest
from freshstack.server import inspect_stack, resolve_constraints, freshness_audit


def test_server_inspect_stack():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    raw = inspect_stack(str(fixture_dir))
    data = json.loads(raw)

    assert data["package_manager"] == "uv"
    assert data["supported_libraries"]["fastapi"] == "0.115.0"
    assert data["supported_libraries"]["pydantic"] == "2.9.2"


def test_server_resolve_constraints():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    raw = resolve_constraints(
        task_description="Build schema",
        libraries={"fastapi": "0.115.0", "pydantic": "2.9.2"},
        project_dir=str(fixture_dir)
    )
    data = json.loads(raw)

    assert data["confidence"] == "VERIFIED"
    assert len(data["deprecated_patterns"]) > 0
    assert len(data["evidence_sources"]) > 0


def test_server_freshness_audit():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    code = "from pydantic import BaseModel\nm = BaseModel()\nd = m.dict()"
    raw = freshness_audit(code, project_dir=str(fixture_dir))
    data = json.loads(raw)

    assert data["clean"] is False
    assert data["violations_count"] >= 1
    assert data["violations"][0]["detected_pattern"] == ".dict()"
