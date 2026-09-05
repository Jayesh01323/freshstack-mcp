"""Unit tests for deterministic freshness audit."""

from pathlib import Path
import pytest
from freshstack.audit import FreshnessAuditor, freshness_audit
from freshstack.models import Confidence, FreshnessAuditReport, Severity


def test_audit_pydantic_v1_deprecated_patterns():
    code = """
from pydantic import BaseModel, validator, BaseSettings

class UserSettings(BaseSettings):
    class Config:
        env_prefix = "APP_"

class UserModel(BaseModel):
    name: str

    @validator("name")
    def check_name(cls, v):
        return v.title()

user = UserModel(name="alice")
data = user.dict()
raw = user.json()
"""
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    auditor = FreshnessAuditor(str(fixture_dir))
    report: FreshnessAuditReport = auditor.audit(code)

    assert not report.clean
    assert report.violations_count >= 5

    patterns = [v.detected_pattern for v in report.violations]
    assert "from pydantic import validator" in patterns
    assert "from pydantic import BaseSettings" in patterns
    assert "class Config:" in patterns
    assert ".dict()" in patterns
    assert "@validator(...)" in patterns

    # Verify all violations have verified confidence and authoritative evidence
    for v in report.violations:
        assert v.confidence == Confidence.VERIFIED
        assert v.evidence.url is not None
        assert v.recommended_replacement != ""


def test_audit_fastapi_and_sqlalchemy_patterns():
    code = """
from fastapi import FastAPI
from sqlalchemy.ext.declarative import declarative_base

app = FastAPI()
Base = declarative_base()

@app.on_event("startup")
async def startup_event():
    pass

def get_user(db, user_id: int):
    return db.query(User).filter(User.id == user_id).first()
"""
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    auditor = FreshnessAuditor(str(fixture_dir))
    report: FreshnessAuditReport = auditor.audit(code)

    assert not report.clean
    patterns = [v.detected_pattern for v in report.violations]
    assert "@app.on_event(...)" in patterns
    assert "db.query(...)" in patterns
    assert "from sqlalchemy.ext.declarative import declarative_base" in patterns


def test_audit_clean_modern_code():
    code = """
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import select

class Base(DeclarativeBase):
    pass

class UserModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str

    @field_validator("name")
    @classmethod
    def check_name(cls, v: str) -> str:
        return v.title()

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(lifespan=lifespan)

user = UserModel(name="alice")
dumped = user.model_dump()
"""
    fixture_dir = Path(__file__).parent / "fixtures" / "sample_uv"
    auditor = FreshnessAuditor(str(fixture_dir))
    report: FreshnessAuditReport = auditor.audit(code)

    assert report.clean
    assert report.violations_count == 0
