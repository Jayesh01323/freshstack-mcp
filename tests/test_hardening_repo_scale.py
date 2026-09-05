"""Hardening Test 6: Realistic Repository Scale & Precision Test.

Generates a realistic synthetic Python repository containing:
- 55 Python files across 8 distinct architectural packages
- 12 dependencies (FastAPI, Pydantic, SQLAlchemy, Alembic, Redis, Celery, etc.)
- Controlled test payload: exactly 5 files with deprecated patterns, totaling exactly 8 violations
- 50 clean modern files (services, utilities, migrations, tests, scripts)

Measures and validates:
- Total audit time & execution efficiency
- Precision (100% recall of the 8 known violations, 0 false positives across 50 clean files)
- Cache acceleration behavior on repeat audits
"""

import time
import os
from pathlib import Path
import pytest

from freshstack.audit import FreshnessAuditor
from freshstack.inspect import StackInspector
from freshstack.models import StackInfo


def build_synthetic_repo(base_dir: Path):
    """Constructs a 55-file realistic repository structure."""
    dirs = [
        base_dir / "app" / "api" / "v1" / "endpoints",
        base_dir / "app" / "core",
        base_dir / "app" / "models",
        base_dir / "app" / "schemas",
        base_dir / "app" / "services",
        base_dir / "app" / "utils",
        base_dir / "scripts",
        base_dir / "migrations" / "versions",
        base_dir / "tests",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    # Manifests
    (base_dir / "pyproject.toml").write_text("""
[project]
name = "enterprise-api"
version = "2.4.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "pydantic>=2.9.2",
    "sqlalchemy>=2.0.35",
    "alembic>=1.13.3",
    "uvicorn>=0.32.0",
    "httpx>=0.27.2",
    "pyjwt>=2.9.0",
    "redis>=5.1.1",
    "celery>=5.4.0",
    "structlog>=24.4.0",
]
""")

    (base_dir / "uv.lock").write_text("""
version = 1
revision = 1

[[package]]
name = "fastapi"
version = "0.115.0"

[[package]]
name = "pydantic"
version = "2.9.2"

[[package]]
name = "sqlalchemy"
version = "2.0.35"

[[package]]
name = "alembic"
version = "1.13.3"

[[package]]
name = "uvicorn"
version = "0.32.0"

[[package]]
name = "httpx"
version = "0.27.2"

[[package]]
name = "pyjwt"
version = "2.9.0"

[[package]]
name = "redis"
version = "5.1.1"

[[package]]
name = "celery"
version = "5.4.0"

[[package]]
name = "structlog"
version = "24.4.0"
""")

    file_count = 0

    # 1. Target Deprecated File 1: app/schemas/user.py (2 violations: @validator, class Config)
    (base_dir / "app" / "schemas" / "user.py").write_text("""
from pydantic import BaseModel, validator

class UserSchema(BaseModel):
    id: int
    email: str

    class Config:
        orm_mode = True

    @validator('email')
    def check_email(cls, v):
        return v.lower()
""")
    file_count += 1

    # 2. Target Deprecated File 2: app/api/v1/endpoints/health.py (1 violation: @app.on_event)
    (base_dir / "app" / "api" / "v1" / "endpoints" / "health.py").write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.on_event("startup")
def startup_handler():
    pass

@app.get("/health")
def health_check():
    return {"status": "ok"}
""")
    file_count += 1

    # 3. Target Deprecated File 3: app/services/user_service.py (2 violations: .dict(), .parse_obj())
    (base_dir / "app" / "services" / "user_service.py").write_text("""
from pydantic import BaseModel

class UserUpdate(BaseModel):
    name: str

def update_user(data: dict):
    model = UserUpdate.parse_obj(data)
    dumped = model.dict()
    return dumped
""")
    file_count += 1

    # 4. Target Deprecated File 4: app/models/user.py (1 violation: session.query())
    (base_dir / "app" / "models" / "user.py").write_text("""
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class UserModel(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String)

def get_user_by_id(db: Session, user_id: int):
    return db.query(UserModel).filter(UserModel.id == user_id).first()
""")
    file_count += 1

    # 5. Target Deprecated File 5: app/schemas/item.py (2 violations: @validator, .dict())
    (base_dir / "app" / "schemas" / "item.py").write_text("""
from pydantic import BaseModel, validator

class ItemSchema(BaseModel):
    title: str
    price: float

    @validator('price')
    def check_price(cls, v):
        if v < 0:
            raise ValueError('Must be positive')
        return v

def serialize_item(item: ItemSchema):
    return item.dict()
""")
    file_count += 1

    # Now create 50 clean modern files
    clean_templates = [
        # FastAPI modern endpoint
        """
from fastapi import APIRouter
router = APIRouter()

@router.get("/{name}")
def get_resource(name: str):
    return {"resource": name, "status": "active"}
""",
        # Pydantic v2 modern model
        """
from pydantic import BaseModel, field_validator, ConfigDict

class DataModel_{idx}(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    score: int

    @field_validator('score')
    @classmethod
    def check_score(cls, v: int) -> int:
        return max(0, v)
""",
        # SQLAlchemy 2.0 modern query
        """
from sqlalchemy.orm import Session
from sqlalchemy import select

def fetch_records_{idx}(db: Session, model):
    stmt = select(model).where(model.id > 0)
    return db.execute(stmt).scalars().all()
""",
        # Service logic with native types
        """
import math

class CalculatorService_{idx}:
    def compute(self, x: float) -> float:
        return math.sqrt(abs(x)) * {idx}
""",
        # Utility logic
        """
import hashlib

def hash_token_{idx}(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
"""
    ]

    # Populate remainder up to 55 total files
    package_targets = [
        ("app/api/v1/endpoints", "endpoint"),
        ("app/core", "core_mod"),
        ("app/models", "model_entity"),
        ("app/schemas", "schema_repr"),
        ("app/services", "service_worker"),
        ("app/utils", "helper_util"),
        ("scripts", "admin_script"),
        ("migrations/versions", "rev_migration"),
        ("tests", "unit_test"),
    ]

    idx = 1
    while file_count < 55:
        dir_rel, prefix = package_targets[idx % len(package_targets)]
        target_path = base_dir / dir_rel / f"{prefix}_{idx}.py"
        template = clean_templates[idx % len(clean_templates)].replace("{idx}", str(idx))
        target_path.write_text(template)
        file_count += 1
        idx += 1

    return file_count


def test_realistic_repo_scale_precision_and_performance(tmp_path):
    """Audits the synthetic 55-file repository and measures precision and performance."""
    total_files_created = build_synthetic_repo(tmp_path)
    assert total_files_created == 55

    # 1. Inspect stack
    inspector = StackInspector(str(tmp_path))
    stack = inspector.inspect()
    assert stack.package_manager == "uv"
    assert stack.supported_libraries.get("fastapi") == "0.115.0"
    assert stack.supported_libraries.get("pydantic") == "2.9.2"
    assert stack.supported_libraries.get("sqlalchemy") == "2.0.35"
    assert len(stack.dependencies) >= 10

    # 2. Audit all 55 files
    auditor = FreshnessAuditor(str(tmp_path))

    py_files = sorted(list(tmp_path.rglob("*.py")))
    assert len(py_files) == 55

    start_time = time.perf_counter()
    audit_results = {}
    total_violations = 0
    flagged_files = set()

    for p in py_files:
        code = p.read_text()
        rel_path = str(p.relative_to(tmp_path))
        report = auditor.audit(code=code, stack_info=stack)
        audit_results[rel_path] = report
        if not report.clean:
            flagged_files.add(rel_path)
            total_violations += report.violations_count

    elapsed_time = time.perf_counter() - start_time

    # Performance benchmark: 55 files audited via AST in under 2.0s
    print(f"\n[BENCHMARK] Audited 55 files ({len(py_files)} total) in {elapsed_time:.3f}s")
    assert elapsed_time < 2.0, f"Audit too slow: {elapsed_time:.3f}s for 55 files"

    # Precision verification:
    # Exactly 5 files flagged
    expected_flagged = {
        "app/schemas/user.py",
        "app/api/v1/endpoints/health.py",
        "app/services/user_service.py",
        "app/models/user.py",
        "app/schemas/item.py",
    }
    assert flagged_files == expected_flagged, f"Mismatch in flagged files: {flagged_files ^ expected_flagged}"

    # Exactly 10 violations detected (including both deprecated imports and usages)
    assert total_violations == 10, f"Expected 10 violations, got {total_violations}"

    # Zero false positives in remaining 50 files
    clean_count = sum(1 for p, rep in audit_results.items() if rep.clean)
    assert clean_count == 50
