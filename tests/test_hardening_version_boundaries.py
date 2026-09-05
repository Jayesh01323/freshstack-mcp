"""Hardening Test 4: Version Boundary Testing.

Tests that deprecation and constraint rules activate ONLY for the exact versions
for which they are authoritative:

- FastAPI:
  * 0.92.0: before lifespan was introduced; on_event is VALID and not deprecated
  * 0.93.0: lifespan introduced; on_event is flagged as deprecated
  * 0.115.0: modern; lifespan is standard

- Pydantic:
  * 1.10.18: legacy v1; @validator, .dict(), .parse_obj(), class Config are VALID
  * 2.0.0: v2 boundary; legacy patterns flagged as deprecated
  * 2.9.2: modern v2; legacy patterns flagged as deprecated

- SQLAlchemy:
  * 1.4.52: 1.x transitional; session.query() is VALID and not deprecated
  * 2.0.0 / 2.0.35: 2.0 style queries required; session.query() is deprecated
"""

import pytest
from freshstack.audit import FreshnessAuditor
from freshstack.knowledge import get_rules_for_package
from freshstack.resolve import ConstraintResolver


def test_fastapi_version_boundaries():
    """Verify FastAPI rules activate strictly at >=0.93.0 for lifespan/on_event."""
    # 0.92.0 - Before lifespan
    rules_92 = get_rules_for_package("fastapi", "0.92.0")
    apis_92 = [r.api_name for r in rules_92]
    assert not any("on_event" in api for api in apis_92)

    # 0.93.0 - Lifespan introduced
    rules_93 = get_rules_for_package("fastapi", "0.93.0")
    apis_93 = [r.api_name for r in rules_93]
    assert any("on_event" in api for api in apis_93)

    # 0.115.0 - Modern
    rules_115 = get_rules_for_package("fastapi", "0.115.0")
    apis_115 = [r.api_name for r in rules_115]
    assert any("on_event" in api for api in apis_115)


def test_pydantic_version_boundaries():
    """Verify Pydantic rules activate strictly at >=2.0.0."""
    # 1.10.18 - Legacy Pydantic v1
    rules_v1 = get_rules_for_package("pydantic", "1.10.18")
    assert len(rules_v1) == 0  # No v2 deprecation rules apply to v1

    # 2.0.0 - Transition boundary
    rules_v2_0 = get_rules_for_package("pydantic", "2.0.0")
    assert len(rules_v2_0) > 0
    apis_v2_0 = [r.api_name for r in rules_v2_0]
    assert "@validator" in apis_v2_0
    assert "BaseModel.dict()" in apis_v2_0
    assert "BaseModel.parse_obj()" in apis_v2_0
    assert any("class Config" in api for api in apis_v2_0)

    # 2.9.2 - Modern Pydantic v2
    rules_v2_9 = get_rules_for_package("pydantic", "2.9.2")
    assert len(rules_v2_9) == len(rules_v2_0)


def test_sqlalchemy_version_boundaries():
    """Verify SQLAlchemy 2.0 rules activate strictly at >=2.0.0."""
    # 1.4.52 - Legacy ORM query allowed
    rules_1_4 = get_rules_for_package("sqlalchemy", "1.4.52")
    assert len(rules_1_4) == 0

    # 2.0.0 - 2.0 style required
    rules_2_0 = get_rules_for_package("sqlalchemy", "2.0.0")
    apis_2_0 = [r.api_name for r in rules_2_0]
    assert any("session.query" in api for api in apis_2_0)

    # 2.0.35 - Modern 2.0.x
    rules_2_0_35 = get_rules_for_package("sqlalchemy", "2.0.35")
    apis_2_0_35 = [r.api_name for r in rules_2_0_35]
    assert any("session.query" in api for api in apis_2_0_35)


def test_audit_version_boundary_enforcement():
    """Verify that auditing the exact same code produces zero violations for v1
    dependencies, and flags deprecated patterns for v2 dependencies.
    """
    code = (
        "from pydantic import BaseModel, validator\n"
        "class User(BaseModel):\n"
        "    email: str\n"
        "    class Config:\n"
        "        orm_mode = True\n"
        "    @validator('email')\n"
        "    def check_email(cls, v):\n"
        "        return v\n"
        "u = User(email='test@example.com')\n"
        "d = u.dict()\n"
    )

    # Auditing with Pydantic 1.10.18
    auditor = FreshnessAuditor()
    from freshstack.models import StackInfo
    stack_v1 = StackInfo(python_version="3.12", package_manager="uv", project_dir=".", supported_libraries={"pydantic": "1.10.18"})
    report_v1 = auditor.audit(code=code, stack_info=stack_v1)
    assert report_v1.clean is True
    assert report_v1.violations_count == 0

    # Auditing with Pydantic 2.0.0
    stack_v2 = StackInfo(python_version="3.12", package_manager="uv", project_dir=".", supported_libraries={"pydantic": "2.0.0"})
    report_v2 = auditor.audit(code=code, stack_info=stack_v2)
    assert report_v2.clean is False
    assert report_v2.violations_count >= 3
    patterns = [v.detected_pattern for v in report_v2.violations]
    assert "@validator(...)" in patterns
    assert "class Config:" in patterns
    assert ".dict()" in patterns

    # Auditing with Pydantic 2.9.2
    stack_v2_9 = StackInfo(python_version="3.12", package_manager="uv", project_dir=".", supported_libraries={"pydantic": "2.9.2"})
    report_v2_9 = auditor.audit(code=code, stack_info=stack_v2_9)
    assert report_v2_9.clean is False
    assert report_v2_9.violations_count == report_v2.violations_count
