"""Constraint resolution pipeline for FreshStack MCP."""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Union

from freshstack.config import logger
from freshstack.inspect import SUPPORTED_PACKAGES, StackInspector
from freshstack.knowledge import get_rules_for_package
from freshstack.models import (
    APIConstraint,
    Confidence,
    EvidenceSource,
    ResolvedConstraints,
    SourceType,
    StackInfo,
)
from freshstack.pypi import pypi_client


class ConstraintResolver:
    """Resolves technology constraints based strictly on resolved project versions and authoritative evidence."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = project_dir
        self.inspector = StackInspector(project_dir)

    def resolve(
        self,
        task_description: str,
        libraries: Optional[Union[List[str], Dict[str, Optional[str]]]] = None
    ) -> ResolvedConstraints:
        """Resolve technology constraints for the given task and target libraries."""
        # 1. Inspect current project state
        stack: StackInfo = self.inspector.inspect()

        target_libs: Dict[str, Optional[str]] = {}
        if libraries is None:
            # Analyze all supported libraries found in the project or all supported MVP libraries
            if stack.supported_libraries:
                target_libs = dict(stack.supported_libraries)
            else:
                target_libs = {lib: None for lib in SUPPORTED_PACKAGES}
        elif isinstance(libraries, list):
            for lib in libraries:
                norm = lib.lower().replace("_", "-")
                resolved = stack.supported_libraries.get(norm) or (
                    stack.dependencies[norm].resolved_version if norm in stack.dependencies else None
                )
                target_libs[norm] = resolved
        elif isinstance(libraries, dict):
            for lib, ver in libraries.items():
                norm = lib.lower().replace("_", "-")
                resolved = ver or stack.supported_libraries.get(norm)
                target_libs[norm] = resolved

        version_specific_apis: List[APIConstraint] = []
        deprecated_patterns: List[APIConstraint] = []
        recommended_patterns: List[str] = []
        evidence_sources: List[EvidenceSource] = list(stack.evidence)

        overall_confidence = Confidence.VERIFIED

        for lib, version in target_libs.items():
            norm_lib = lib.lower().replace("_", "-")

            if norm_lib not in SUPPORTED_PACKAGES:
                overall_confidence = Confidence.UNKNOWN
                evidence_sources.append(
                    EvidenceSource(
                        source_type=SourceType.AUTHORITATIVE_SOURCE,
                        title=f"Unsupported Library: {lib}",
                        details="Library is outside the Python MVP scope (FastAPI, Pydantic, SQLAlchemy, Alembic)."
                    )
                )
                continue

            # Check if version was pinned or resolved
            if version is None:
                # If neither project pinned it nor registry available, evidence is insufficient -> UNKNOWN
                if norm_lib in pypi_client.last_errors:
                    overall_confidence = Confidence.UNKNOWN
                elif overall_confidence != Confidence.UNKNOWN:
                    overall_confidence = Confidence.INFERRED
                evidence_sources.append(
                    EvidenceSource(
                        source_type=SourceType.PROJECT_FILE,
                        title=f"Unpinned Dependency: {norm_lib}",
                        details=f"No pinned version found for '{norm_lib}' in project files; inferring modern constraints."
                    )
                )
            else:
                # Add registry evidence
                pypi_ev = pypi_client.get_evidence_source(norm_lib, version)
                evidence_sources.append(pypi_ev)
                if "Unavailable" in pypi_ev.title or "Offline" in pypi_ev.title:
                    # Degradation: registry unavailable and not in cache; downgrade confidence
                    if overall_confidence == Confidence.VERIFIED:
                        overall_confidence = Confidence.INFERRED

            # Retrieve authoritative rules
            rules = get_rules_for_package(norm_lib, version)
            for rule in rules:
                api_constraint = APIConstraint(
                    name=rule.api_name,
                    status=rule.status,
                    reason=rule.reason,
                    replacement=rule.replacement,
                    since_version=rule.since_version,
                    evidence=rule.evidence
                )
                if rule.status in ("deprecated", "removed"):
                    deprecated_patterns.append(api_constraint)
                else:
                    version_specific_apis.append(api_constraint)
                evidence_sources.append(rule.evidence)

            # Generate high-level recommended architectural patterns
            if norm_lib == "fastapi":
                recommended_patterns.append(
                    "FastAPI Application Lifecycle: Use lifespan context manager instead of @app.on_event handlers."
                )
                recommended_patterns.append(
                    "FastAPI Response Models: Rely on Pydantic v2 schemas with native serialization."
                )
            elif norm_lib == "pydantic":
                recommended_patterns.append(
                    "Pydantic V2 Models: Use .model_dump() / .model_validate(), and model_config = ConfigDict(...)."
                )
                recommended_patterns.append(
                    "Pydantic Validation: Use @field_validator and @model_validator decorators."
                )
            elif norm_lib == "sqlalchemy":
                recommended_patterns.append(
                    "SQLAlchemy 2.0 ORM: Subclass DeclarativeBase, use mapped_column() and select() executed via session.execute()."
                )
            elif norm_lib == "alembic":
                recommended_patterns.append(
                    "Alembic Migrations: Pass active connection within transaction block for SQLAlchemy 2.0 compatibility."
                )

        # Remove duplicate evidence sources by title and url
        seen = set()
        deduped_evidence = []
        for ev in evidence_sources:
            key = (ev.title, ev.url)
            if key not in seen:
                seen.add(key)
                deduped_evidence.append(ev)

        return ResolvedConstraints(
            task_description=task_description,
            libraries=target_libs,
            version_specific_apis=version_specific_apis,
            deprecated_patterns=deprecated_patterns,
            recommended_patterns=recommended_patterns,
            evidence_sources=deduped_evidence,
            confidence=overall_confidence,
            verification_time=datetime.now(timezone.utc).isoformat()
        )


def resolve_constraints(
    task_description: str,
    libraries: Optional[Union[List[str], Dict[str, Optional[str]]]] = None,
    project_dir: str = "."
) -> ResolvedConstraints:
    """Convenience entry point for constraint resolution."""
    return ConstraintResolver(project_dir).resolve(task_description, libraries)
