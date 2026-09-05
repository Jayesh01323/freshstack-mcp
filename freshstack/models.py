"""Core data models for FreshStack MCP."""

from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class Confidence(str, Enum):
    """Confidence level of technology intelligence."""
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"
    UNKNOWN = "UNKNOWN"


class Severity(str, Enum):
    """Severity of a detected code issue."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class SourceType(str, Enum):
    """Types of authoritative evidence sources."""
    PROJECT_FILE = "project_file"
    OFFICIAL_DOC = "official_doc"
    MIGRATION_GUIDE = "migration_guide"
    CHANGELOG = "changelog"
    PYPI_REGISTRY = "pypi_registry"
    AUTHORITATIVE_SOURCE = "authoritative_source"
    LLM_REASONING = "llm_reasoning"


class EvidenceSource(BaseModel):
    """Authoritative source supporting a constraint, recommendation, or audit."""
    model_config = ConfigDict(frozen=True)

    source_type: SourceType = Field(description="Type of authoritative source")
    title: str = Field(description="Name or title of the source")
    url: Optional[str] = Field(default=None, description="Official documentation or reference URL")
    verified_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp when verification was recorded"
    )
    details: Optional[str] = Field(default=None, description="Quotation or summary of authoritative statement")


class ProjectDependency(BaseModel):
    """A detected or resolved project dependency."""
    model_config = ConfigDict(frozen=True)

    name: str = Field(description="Normalized package name (e.g. fastapi)")
    specifier: Optional[str] = Field(default=None, description="Declared version constraint (e.g. >=0.100.0)")
    resolved_version: Optional[str] = Field(default=None, description="Exact resolved/pinned version (e.g. 0.115.0)")
    source_file: str = Field(description="File where dependency was declared/resolved")


class StackInfo(BaseModel):
    """Result of inspect_stack capability."""
    project_name: Optional[str] = Field(default=None, description="Detected project name")
    python_version: Optional[str] = Field(default=None, description="Detected required Python version")
    package_manager: str = Field(description="Detected package manager (uv, poetry, pip, etc.)")
    detected_files: List[str] = Field(default_factory=list, description="List of recognized manifest/lock files")
    dependencies: Dict[str, ProjectDependency] = Field(
        default_factory=dict,
        description="All detected dependencies mapped by normalized name"
    )
    supported_libraries: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="Supported MVP libraries (FastAPI, Pydantic, SQLAlchemy, Alembic) with resolved versions"
    )
    evidence: List[EvidenceSource] = Field(
        default_factory=list,
        description="Evidence sources used during stack inspection"
    )


class APIConstraint(BaseModel):
    """Specific API constraint or recommendation."""
    name: str = Field(description="API element name (e.g., @app.on_event('startup'))")
    status: str = Field(description="Status: 'deprecated', 'supported', 'removed', 'recommended'")
    reason: str = Field(description="Why this status applies to the resolved version")
    replacement: Optional[str] = Field(default=None, description="Recommended modern pattern")
    since_version: Optional[str] = Field(default=None, description="Version where deprecated/introduced")
    evidence: EvidenceSource = Field(description="Authoritative evidence for this API constraint")


class ResolvedConstraints(BaseModel):
    """Result of resolve_constraints capability."""
    task_description: str = Field(description="Developer task or intent being analyzed")
    libraries: Dict[str, Optional[str]] = Field(
        description="Targeted libraries with their resolved or requested versions"
    )
    version_specific_apis: List[APIConstraint] = Field(
        default_factory=list,
        description="APIs valid and recommended for the exact resolved version"
    )
    deprecated_patterns: List[APIConstraint] = Field(
        default_factory=list,
        description="Deprecated or forbidden patterns for the resolved version"
    )
    recommended_patterns: List[str] = Field(
        default_factory=list,
        description="High-level modern architectural patterns verified for this version"
    )
    evidence_sources: List[EvidenceSource] = Field(
        default_factory=list,
        description="All authoritative sources consulted"
    )
    confidence: Confidence = Field(
        description="Overall confidence level (VERIFIED if authoritative sources confirmed, INFERRED/UNKNOWN otherwise)"
    )
    verification_time: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO timestamp when verification completed"
    )


class AuditViolation(BaseModel):
    """A detected version mismatch, deprecation, or incompatible pattern."""
    severity: Severity = Field(description="Severity: error, warning, info")
    package: str = Field(description="Associated package name")
    version: Optional[str] = Field(default=None, description="Resolved version in project")
    detected_pattern: str = Field(description="The code pattern detected")
    line_number: Optional[int] = Field(default=None, description="1-indexed line number in source code")
    column: Optional[int] = Field(default=None, description="1-indexed column number in source code")
    reason: str = Field(description="Explanation of why the pattern is outdated or invalid")
    recommended_replacement: str = Field(description="Exact modern code replacement or guidance")
    evidence: EvidenceSource = Field(description="Authoritative citation proving deprecation/incompatibility")
    confidence: Confidence = Field(description="VERIFIED or INFERRED")


class FreshnessAuditReport(BaseModel):
    """Result of freshness_audit capability."""
    code_summary: str = Field(description="Summary of code analyzed")
    scanned_lines: int = Field(description="Number of lines scanned")
    violations_count: int = Field(description="Total number of violations found")
    violations: List[AuditViolation] = Field(
        default_factory=list,
        description="Detailed list of violations"
    )
    analyzed_packages: List[str] = Field(
        default_factory=list,
        description="Supported packages detected in the code"
    )
    clean: bool = Field(description="True if no errors or warnings were found")
