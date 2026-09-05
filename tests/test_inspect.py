"""Unit tests for project stack inspection."""

from pathlib import Path
import pytest
from freshstack.inspect import StackInspector, inspect_stack
from freshstack.models import StackInfo


def test_inspect_uv_lock():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    inspector = StackInspector(str(fixture_dir))
    stack: StackInfo = inspector.inspect()

    assert stack.package_manager == "uv"
    assert "uv.lock" in stack.detected_files
    assert "pyproject.toml" in stack.detected_files
    assert stack.project_name == "sample-service"

    # Resolved versions from uv.lock
    assert stack.supported_libraries["fastapi"] == "0.115.0"
    assert stack.supported_libraries["pydantic"] == "2.9.2"
    assert stack.supported_libraries["sqlalchemy"] == "2.0.35"
    assert stack.supported_libraries["alembic"] == "1.13.3"

    # Evidence sources attached
    assert len(stack.evidence) >= 2
    assert any("uv.lock" in ev.title for ev in stack.evidence)


def test_inspect_requirements_txt():
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_reqs"
    inspector = StackInspector(str(fixture_dir))
    stack: StackInfo = inspector.inspect()

    assert stack.package_manager == "pip"
    assert "requirements.txt" in stack.detected_files

    # Pinned versions from requirements.txt
    assert stack.supported_libraries["fastapi"] == "0.115.0"
    assert stack.supported_libraries["pydantic"] == "2.9.2"
    assert stack.supported_libraries["sqlalchemy"] == "2.0.35"
    assert stack.supported_libraries["alembic"] == "1.13.3"


def test_inspect_current_repo():
    # Test inspecting the workspace itself
    stack = inspect_stack(".")
    assert isinstance(stack, StackInfo)
    assert stack.package_manager in ("uv", "pip", "unknown")
