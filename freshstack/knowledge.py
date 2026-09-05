"""Authoritative version knowledge and constraint definitions for supported libraries."""

from typing import Dict, List, Optional
from packaging.specifiers import SpecifierSet
from packaging.version import Version, InvalidVersion

from freshstack.models import APIConstraint, EvidenceSource, SourceType


class VersionRule:
    """A rule defining deprecation, introduction, or replacement for a specific version range."""

    def __init__(
        self,
        package: str,
        specifier: str,
        api_name: str,
        status: str,
        reason: str,
        replacement: Optional[str],
        title: str,
        url: str,
        details: str,
        since_version: Optional[str] = None
    ):
        self.package = package
        self.specifier = SpecifierSet(specifier)
        self.api_name = api_name
        self.status = status
        self.reason = reason
        self.replacement = replacement
        self.since_version = since_version
        self.evidence = EvidenceSource(
            source_type=SourceType.OFFICIAL_DOC if "docs" in url else SourceType.MIGRATION_GUIDE,
            title=title,
            url=url,
            details=details
        )

    def matches(self, version_str: Optional[str]) -> bool:
        """Check if a resolved version matches this rule's specifier."""
        if not version_str:
            # If no version pinned, assume modern package rules apply with INFERRED status
            return True
        try:
            return Version(version_str) in self.specifier
        except InvalidVersion:
            return True


# Authoritative rules grounded strictly in official documentation
AUTHORITATIVE_RULES: List[VersionRule] = [
    # ---------------- FastAPI ----------------
    VersionRule(
        package="fastapi",
        specifier=">=0.93.0",
        api_name='@app.on_event("startup") / @app.on_event("shutdown")',
        status="deprecated",
        reason="on_event startup and shutdown handlers are deprecated in FastAPI in favor of lifespan async context managers.",
        replacement="@asynccontextmanager async def lifespan(app: FastAPI): ...; app = FastAPI(lifespan=lifespan)",
        since_version="0.93.0",
        title="FastAPI Official Documentation - Lifespan Events",
        url="https://fastapi.tiangolo.com/advanced/events/#lifespan",
        details="Official FastAPI docs state: 'You can define logic (code) that should be executed before the application starts up... using the lifespan parameter of the FastAPI app.'"
    ),
    VersionRule(
        package="fastapi",
        specifier=">=0.100.0",
        api_name="model.dict()",
        status="deprecated",
        reason="FastAPI 0.100.0+ supports Pydantic v2 natively. Use modern .model_dump() instead of legacy .dict().",
        replacement="model.model_dump()",
        since_version="0.100.0",
        title="FastAPI 0.100.0 Release Notes & Pydantic v2 Support",
        url="https://fastapi.tiangolo.com/release-notes/#01000",
        details="FastAPI 0.100.0 added full support for Pydantic v2, where .dict() is superseded by .model_dump()."
    ),

    # ---------------- Pydantic ----------------
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="BaseModel.dict()",
        status="deprecated",
        reason=".dict() is deprecated in Pydantic v2. Use .model_dump() instead.",
        replacement="model.model_dump(mode='python')",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Model Methods",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-pydanticbasemodel",
        details="Official Pydantic v2 migration guide notes: 'BaseModel.dict() is deprecated, use BaseModel.model_dump() instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="BaseModel.json()",
        status="deprecated",
        reason=".json() is deprecated in Pydantic v2. Use .model_dump_json() instead.",
        replacement="model.model_dump_json()",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Model Methods",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-pydanticbasemodel",
        details="Official Pydantic v2 migration guide notes: 'BaseModel.json() is deprecated, use BaseModel.model_dump_json() instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="BaseModel.parse_obj()",
        status="deprecated",
        reason=".parse_obj() is deprecated in Pydantic v2. Use .model_validate() instead.",
        replacement="MyModel.model_validate(obj)",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Parsing and Validation",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-pydanticbasemodel",
        details="Official Pydantic v2 migration guide: 'BaseModel.parse_obj() is deprecated, use BaseModel.model_validate() instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="BaseModel.parse_raw()",
        status="deprecated",
        reason=".parse_raw() is deprecated in Pydantic v2. Use .model_validate_json() instead.",
        replacement="MyModel.model_validate_json(raw_str)",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Parsing and Validation",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-pydanticbasemodel",
        details="Official Pydantic v2 migration guide: 'BaseModel.parse_raw() is deprecated, use BaseModel.model_validate_json() instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="class Config: inside BaseModel",
        status="deprecated",
        reason="Inner 'class Config:' is deprecated in Pydantic v2. Use model_config = ConfigDict(...) instead.",
        replacement="model_config = ConfigDict(from_attributes=True, extra='forbid')",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Configuration",
        url="https://docs.pydantic.dev/latest/migration/#changes-to-config",
        details="Official Pydantic v2 guide: 'The Config class inside models is deprecated; use model_config = ConfigDict(...) attribute instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="@validator",
        status="deprecated",
        reason="@validator is deprecated in Pydantic v2. Use @field_validator instead.",
        replacement="@field_validator('field_name')\ndef validate_field(cls, v): return v",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Validators",
        url="https://docs.pydantic.dev/latest/migration/#validators",
        details="Official Pydantic v2 guide: '@validator is deprecated; use @field_validator instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="@root_validator",
        status="deprecated",
        reason="@root_validator is deprecated in Pydantic v2. Use @model_validator instead.",
        replacement="@model_validator(mode='after')\ndef validate_model(self): return self",
        since_version="2.0.0",
        title="Pydantic V2 Migration Guide - Model Validators",
        url="https://docs.pydantic.dev/latest/migration/#validators",
        details="Official Pydantic v2 guide: '@root_validator is deprecated; use @model_validator(mode='before' | 'after') instead.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="from pydantic import BaseSettings",
        status="deprecated",
        reason="BaseSettings was moved out of core Pydantic in v2 into the pydantic-settings standalone package.",
        replacement="from pydantic_settings import BaseSettings, SettingsConfigDict",
        since_version="2.0.0",
        title="Pydantic Settings Standalone Library",
        url="https://docs.pydantic.dev/latest/migration/#basesettings-has-moved-to-pydantic-settings",
        details="Official Pydantic v2 guide: 'BaseSettings has moved to a separate repository and package: pydantic-settings.'"
    ),
    VersionRule(
        package="pydantic",
        specifier=">=2.0.0",
        api_name="Field(regex=...)",
        status="deprecated",
        reason="The 'regex' argument to Field() is deprecated in Pydantic v2. Use 'pattern' instead.",
        replacement="Field(pattern=r'^[a-z]+$')",
        since_version="2.0.0",
        title="Pydantic V2 Field Constraints",
        url="https://docs.pydantic.dev/latest/concepts/fields/#string-constraints",
        details="Official Pydantic v2 guide: 'Use pattern instead of regex in Field constraints.'"
    ),

    # ---------------- SQLAlchemy ----------------
    VersionRule(
        package="sqlalchemy",
        specifier=">=2.0.0",
        api_name="session.query(Model)",
        status="deprecated",
        reason="session.query() is the legacy 1.x Query interface. In SQLAlchemy 2.0+, use session.execute(select(Model)).scalars() instead.",
        replacement="session.execute(select(Model).where(Model.id == 1)).scalars().all()",
        since_version="2.0.0",
        title="SQLAlchemy 2.0 Migration Guide - 2.0 Style Executable Queries",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-usage",
        details="Official SQLAlchemy 2.0 guide: 'Query is superseded by the 2.0 style select() construct executed via Session.execute()'."
    ),
    VersionRule(
        package="sqlalchemy",
        specifier=">=2.0.0",
        api_name="declarative_base()",
        status="deprecated",
        reason="declarative_base() function is legacy. In SQLAlchemy 2.0+, subclass DeclarativeBase from sqlalchemy.orm instead.",
        replacement="from sqlalchemy.orm import DeclarativeBase\n\nclass Base(DeclarativeBase):\n    pass",
        since_version="2.0.0",
        title="SQLAlchemy 2.0 Migration Guide - Declarative Base Class",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-orm-declarative",
        details="Official SQLAlchemy 2.0 guide: 'The declarative_base() function is superseded by the DeclarativeBase superclass.'"
    ),
    VersionRule(
        package="sqlalchemy",
        specifier=">=2.0.0",
        api_name="engine.execute('...')",
        status="removed",
        reason="Direct engine.execute() was removed in SQLAlchemy 2.0. All execution must use an explicit connection context.",
        replacement="with engine.connect() as conn:\n    result = conn.execute(text('SELECT 1'))",
        since_version="2.0.0",
        title="SQLAlchemy 2.0 Migration Guide - Engine Execution",
        url="https://docs.sqlalchemy.org/en/20/changelog/migration_20.html#migration-engine-connection",
        details="Official SQLAlchemy 2.0 guide: 'Connection-less execution via engine.execute() has been completely removed.'"
    ),

    # ---------------- Alembic ----------------
    VersionRule(
        package="alembic",
        specifier=">=1.12.0",
        api_name="legacy connection-less migration",
        status="deprecated",
        reason="Alembic 1.12.0+ aligns with SQLAlchemy 2.0. Online migrations must pass an engine connection with transaction block.",
        replacement="with connectable.connect() as connection:\n    context.configure(connection=connection, target_metadata=target_metadata)",
        since_version="1.12.0",
        title="Alembic Official Migration Tutorial",
        url="https://alembic.sqlalchemy.org/en/latest/tutorial.html",
        details="Official Alembic docs mandate connection context blocks for SQLAlchemy 2.0 compatibility."
    ),
]


def get_rules_for_package(package_name: str, resolved_version: Optional[str] = None) -> List[VersionRule]:
    """Retrieve all authoritative rules matching a package and version."""
    norm_pkg = package_name.lower().replace("_", "-")
    matching = []
    for rule in AUTHORITATIVE_RULES:
        if rule.package == norm_pkg and rule.matches(resolved_version):
            matching.append(rule)
    return matching
