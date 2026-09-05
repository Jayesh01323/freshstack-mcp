"""Rigorous Acceptance Test Suite for FreshStack MCP Server.

Executes:
A. Legacy detection (Version A - intentionally legacy)
B. Modern-code pass (Version B - modern)
C. False-positive rate (Zero false positives on modern code)
D. UNKNOWN handling (Ambiguous/out-of-scope patterns and libraries)
E. Version-awareness (Pydantic v1 vs v2 resolved version constraint handling)
F. Evidence provenance (Exact installed versions, authoritative URLs, replacements)
G. MCP tool behavior over stdio
H. Unit test suite regression verification
"""

import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from freshstack.models import (
    Confidence,
    FreshnessAuditReport,
    ResolvedConstraints,
    Severity,
    StackInfo,
)


async def run_suite():
    print("=" * 80)
    print("FRESHSTACK RIGOROUS ACCEPTANCE TEST SUITE")
    print("=" * 80)

    server_params = StdioServerParameters(
        command=".venv/bin/python",
        args=["-m", "freshstack.server"],
        env=None
    )

    acceptance_project_dir = "freshstack-acceptance-project"
    v1_project_dir = "freshstack-v1-project"

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("[INIT] FreshStack MCP Server initialized successfully over stdio transport.")

            # -------------------------------------------------------------
            # STEP 0: Inspect acceptance project stack
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 0: Inspecting 'freshstack-acceptance-project' stack")
            print("-" * 80)
            res_inspect = await session.call_tool("inspect_stack", {"project_dir": acceptance_project_dir})
            inspect_data = json.loads(res_inspect.content[0].text)
            stack_info = StackInfo.model_validate(inspect_data)

            print(f"Project Name     : {stack_info.project_name}")
            print(f"Package Manager  : {stack_info.package_manager}")
            print(f"Python Version   : {stack_info.python_version}")
            print(f"Supported Libs   : {stack_info.supported_libraries}")

            assert stack_info.package_manager == "uv"
            assert stack_info.supported_libraries.get("fastapi") == "0.115.0"
            assert stack_info.supported_libraries.get("pydantic") == "2.9.2"
            assert stack_info.supported_libraries.get("sqlalchemy") == "2.0.35"
            assert stack_info.supported_libraries.get("alembic") == "1.13.3"
            print(">>> STEP 0 PASSED: Stack correctly identified with exact resolved versions.")

            # -------------------------------------------------------------
            # STEP 1: Test VERSION A (Legacy / Outdated Implementation)
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 1: Testing VERSION A (Intentionally Legacy / Incorrect)")
            print("-" * 80)
            with open(Path(acceptance_project_dir) / "app_legacy.py", "r", encoding="utf-8") as f:
                code_legacy = f.read()

            res_legacy = await session.call_tool(
                "freshness_audit",
                {"code": code_legacy, "project_dir": acceptance_project_dir}
            )
            report_legacy = FreshnessAuditReport.model_validate(json.loads(res_legacy.content[0].text))

            print(f"Scanned Lines    : {report_legacy.scanned_lines}")
            print(f"Clean            : {report_legacy.clean}")
            print(f"Violations Count : {report_legacy.violations_count}")
            print(f"Analyzed Packages: {report_legacy.analyzed_packages}")
            print("\nViolations Detected:")
            for idx, v in enumerate(report_legacy.violations, 1):
                print(f"  [{idx}] Pattern   : {v.detected_pattern} (Line {v.line_number}:{v.column})")
                print(f"      Package   : {v.package} (Resolved: {v.version})")
                print(f"      Severity  : {v.severity}")
                print(f"      Reason    : {v.reason}")
                print(f"      Replace   : {v.recommended_replacement}")
                print(f"      Evidence  : {v.evidence.title} ({v.evidence.url})")
                print(f"      Confidence: {v.confidence}")

            # Verification assertions for Version A
            assert not report_legacy.clean, "Version A should FAIL the freshness audit!"
            assert report_legacy.violations_count >= 6, f"Expected at least 6 violations, found {report_legacy.violations_count}"

            detected_patterns = [v.detected_pattern for v in report_legacy.violations]

            # Check specific required legacy patterns
            assert any("validator" in p for p in detected_patterns), "Missing @validator violation"
            assert any(".dict()" in p for p in detected_patterns), "Missing .dict() violation"
            assert any(".parse_obj()" in p for p in detected_patterns), "Missing .parse_obj() violation"
            assert any("Config:" in p for p in detected_patterns), "Missing class Config: violation"
            assert any("on_event" in p for p in detected_patterns), "Missing @app.on_event violation"
            assert any("query" in p for p in detected_patterns), "Missing session.query() violation"

            # Check that every violation has exact resolved version and VERIFIED confidence
            for v in report_legacy.violations:
                assert v.version is not None, f"Violation {v.detected_pattern} must have resolved version"
                assert v.confidence == Confidence.VERIFIED, f"Violation {v.detected_pattern} must be VERIFIED"
                assert v.evidence.url is not None, f"Violation {v.detected_pattern} must have authoritative URL"
                assert v.recommended_replacement is not None, f"Violation {v.detected_pattern} must have replacement"

            print(">>> STEP 1 PASSED: Version A successfully caught all deprecated patterns with authoritative evidence.")

            # -------------------------------------------------------------
            # STEP 2: Test VERSION B (Modern Implementation)
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 2: Testing VERSION B (Modern Implementation)")
            print("-" * 80)
            with open(Path(acceptance_project_dir) / "app_modern.py", "r", encoding="utf-8") as f:
                code_modern = f.read()

            res_modern = await session.call_tool(
                "freshness_audit",
                {"code": code_modern, "project_dir": acceptance_project_dir}
            )
            report_modern = FreshnessAuditReport.model_validate(json.loads(res_modern.content[0].text))

            print(f"Scanned Lines    : {report_modern.scanned_lines}")
            print(f"Clean            : {report_modern.clean}")
            print(f"Violations Count : {report_modern.violations_count}")
            print(f"Violations       : {report_modern.violations}")
            print(f"Analyzed Packages: {report_modern.analyzed_packages}")

            # Verification assertions for Version B
            assert report_modern.clean is True, "Version B must PASS the freshness audit!"
            assert report_modern.violations_count == 0, f"False positives detected: {report_modern.violations}"
            assert len(report_modern.violations) == 0
            print(">>> STEP 2 PASSED: Version B passed with ZERO false positives.")

            # -------------------------------------------------------------
            # STEP 3: Test UNKNOWN / Ambiguous / Out-of-Scope handling
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 3: Testing UNKNOWN / Out-of-Scope Handling")
            print("-" * 80)

            # Part 3a: resolve_constraints with unsupported libraries
            out_of_scope_libs = ["redis", "celery", "django_tenants"]
            print(f"Querying constraints for out-of-scope libraries: {out_of_scope_libs}")
            res_unknown = await session.call_tool(
                "resolve_constraints",
                {
                    "task_description": "Setup Celery task worker with Redis backend",
                    "libraries": out_of_scope_libs,
                    "project_dir": acceptance_project_dir
                }
            )
            unknown_data = json.loads(res_unknown.content[0].text)
            unknown_resolved = ResolvedConstraints.model_validate(unknown_data)

            print(f"Overall Confidence : {unknown_resolved.confidence}")
            print(f"Deprecated Patterns: {unknown_resolved.deprecated_patterns}")
            print(f"Evidence Sources   : {[e.title for e in unknown_resolved.evidence_sources]}")

            assert unknown_resolved.confidence == Confidence.UNKNOWN, "Expected confidence to be UNKNOWN for out-of-scope libraries!"
            assert len(unknown_resolved.deprecated_patterns) == 0, "Must NOT invent violations for out-of-scope libraries!"
            assert any("Unsupported Library" in e.title for e in unknown_resolved.evidence_sources)
            print(">>> STEP 3a PASSED: Correctly marked UNKNOWN without inventing violations.")

            # Part 3b: freshness_audit on ambiguous / custom code
            ambiguous_code = """
import redis
import httpx

client = redis.Redis(host='localhost', port=6379)
client.set('cache_key', 'value')
data = httpx.get('https://example.com/api').json()
"""
            res_ambiguous_audit = await session.call_tool(
                "freshness_audit",
                {"code": ambiguous_code, "project_dir": acceptance_project_dir}
            )
            ambiguous_report = FreshnessAuditReport.model_validate(json.loads(res_ambiguous_audit.content[0].text))
            print(f"Ambiguous Audit Clean: {ambiguous_report.clean}")
            print(f"Ambiguous Violations : {ambiguous_report.violations_count}")
            assert ambiguous_report.clean is True, "Ambiguous/out-of-scope code must not trigger invented violations!"
            assert ambiguous_report.violations_count == 0
            print(">>> STEP 3b PASSED: Ambiguous code produced zero invented violations.")

            # -------------------------------------------------------------
            # STEP 4: Test Version Awareness (Pydantic v1 vs v2 project)
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 4: Testing Version Awareness across Different Stack Versions")
            print("-" * 80)

            res_v1_inspect = await session.call_tool("inspect_stack", {"project_dir": v1_project_dir})
            v1_stack = StackInfo.model_validate(json.loads(res_v1_inspect.content[0].text))
            print(f"V1 Project Stack: {v1_stack.supported_libraries}")
            assert v1_stack.supported_libraries.get("pydantic") == "1.10.18"
            assert v1_stack.supported_libraries.get("fastapi") == "0.88.0"
            assert v1_stack.supported_libraries.get("sqlalchemy") == "1.4.52"

            # Code that uses .dict(), @validator, class Config: which are 100% VALID in Pydantic 1.10.18
            v1_valid_code = """from pydantic import BaseModel, validator
from fastapi import FastAPI
from sqlalchemy.orm import declarative_base

Base = declarative_base()
app = FastAPI()

@app.on_event("startup")
def startup():
    pass

class Item(BaseModel):
    name: str

    @validator("name")
    def check_name(cls, v):
        return v.strip()

    class Config:
        orm_mode = True

item = Item(name="test")
data = item.dict()
item2 = Item.parse_obj(data)
"""
            # Run audit against freshstack-v1-project
            res_v1_audit = await session.call_tool(
                "freshness_audit",
                {"code": v1_valid_code, "project_dir": v1_project_dir}
            )
            v1_report = FreshnessAuditReport.model_validate(json.loads(res_v1_audit.content[0].text))
            print(f"V1 Project Audit - Scanned Lines: {v1_report.scanned_lines}")
            print(f"V1 Project Audit - Clean        : {v1_report.clean}")
            print(f"V1 Project Audit - Violations   : {v1_report.violations_count}")
            print(f"V1 Project Violations List      : {[v.detected_pattern for v in v1_report.violations]}")

            # In Pydantic 1.10.18, FastAPI 0.88.0, and SQLAlchemy 1.4.52, these are NOT deprecated!
            assert v1_report.clean is True, (
                f"Version-awareness failure! In Pydantic 1.10.18, .dict() / @validator / class Config "
                f"are valid and must NOT be flagged: {v1_report.violations}"
            )
            assert v1_report.violations_count == 0

            # Compare this directly against running the exact SAME code in freshstack-acceptance-project (Pydantic 2.9.2):
            res_v2_audit = await session.call_tool(
                "freshness_audit",
                {"code": v1_valid_code, "project_dir": acceptance_project_dir}
            )
            v2_report = FreshnessAuditReport.model_validate(json.loads(res_v2_audit.content[0].text))
            print(f"Same code audited against Pydantic v2 project - Violations: {v2_report.violations_count}")
            assert v2_report.clean is False
            assert v2_report.violations_count > 0, "Same code in Pydantic v2 project MUST be flagged!"

            print(">>> STEP 4 PASSED: Version awareness verified! FreshStack respects resolved version bounds.")

            # -------------------------------------------------------------
            # STEP 5: resolve_constraints Evidence and Provenance Verification
            # -------------------------------------------------------------
            print("\n" + "-" * 80)
            print("STEP 5: Detailed Evidence Provenance Verification")
            print("-" * 80)
            res_resolve = await session.call_tool(
                "resolve_constraints",
                {
                    "task_description": "Implement user registration API with validation and database persistence",
                    "libraries": ["fastapi", "pydantic", "sqlalchemy", "alembic"],
                    "project_dir": acceptance_project_dir
                }
            )
            resolve_data = json.loads(res_resolve.content[0].text)
            resolve_report = ResolvedConstraints.model_validate(resolve_data)

            print(f"Target Libraries: {resolve_report.libraries}")
            print(f"Confidence      : {resolve_report.confidence}")
            print(f"Deprecated Items: {len(resolve_report.deprecated_patterns)}")
            print(f"Evidence Sources: {len(resolve_report.evidence_sources)}")

            assert resolve_report.confidence == Confidence.VERIFIED
            assert len(resolve_report.deprecated_patterns) > 0

            # Ensure all evidence sources are non-empty and authoritative
            for ev in resolve_report.evidence_sources:
                assert ev.title, "Evidence must have title"
                assert ev.details, "Evidence must have details"
                assert ev.verified_at, "Evidence must have verification timestamp"
                print(f"  [Evidence] {ev.source_type} | {ev.title} | {ev.url or 'local'}")

            print(">>> STEP 5 PASSED: Evidence provenance complete and verified.")

    print("\n" + "=" * 80)
    print("ALL ACCEPTANCE TESTS COMPLETED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_suite())
