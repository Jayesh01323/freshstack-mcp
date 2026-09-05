"""End-to-end verification script for FreshStack MCP server."""

import asyncio
import json
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from freshstack.models import FreshnessAuditReport, ResolvedConstraints, StackInfo


async def run_validation():
    print("=" * 80)
    print("FRESHSTACK MCP END-TO-END VALIDATION SUITE")
    print("=" * 80)

    server_params = StdioServerParameters(
        command=".venv/bin/python",
        args=["-m", "freshstack.server"],
        env=None
    )

    results = {}

    # Step 1 & 2: Start server via stdio entrypoint and verify no errors
    print("\n[STEP 1 & 2] Starting FreshStack MCP server using stdio transport...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            init_result = await session.initialize()
            print(f"Server Name: {init_result.server_info.name}")
            print(f"Instructions: {init_result.instructions}")
            print(f"Protocol Version: {init_result.protocol_version}")
            assert init_result.server_info.name == "freshstack-mcp"
            results["server_startup"] = "PASS"
            print(">>> MCP server startup: PASS")

            # Step 3: Verify all three tools are registered
            print("\n[STEP 3] Verifying registered tools...")
            tools_list = await session.list_tools()
            tool_names = [t.name for t in tools_list.tools]
            print(f"Registered tools: {tool_names}")
            expected_tools = {"inspect_stack", "resolve_constraints", "freshness_audit"}
            assert expected_tools.issubset(set(tool_names)), f"Missing tools: {expected_tools - set(tool_names)}"
            results["tool_registration"] = "PASS"
            print(">>> Tool registration: PASS")

            # Step 4, 5, 6: Execute each tool against test project and verify schemas
            fixture_dir = "tests/fixtures/sample_uv"
            print(f"\n[STEP 4, 5, 6] Executing inspect_stack against '{fixture_dir}'...")
            res_inspect = await session.call_tool("inspect_stack", {"project_dir": fixture_dir})
            inspect_text = res_inspect.content[0].text
            print("=== EXACT inspect_stack OUTPUT ===")
            print(inspect_text)
            inspect_dict = json.loads(inspect_text)
            # Schema validation
            stack_model = StackInfo.model_validate(inspect_dict)
            assert stack_model.package_manager == "uv"
            assert "fastapi" in stack_model.supported_libraries
            results["inspect_stack"] = "PASS"
            print(">>> inspect_stack: PASS (Matches StackInfo schema)")

            print(f"\n[STEP 4, 5, 6] Executing resolve_constraints against '{fixture_dir}'...")
            res_resolve = await session.call_tool(
                "resolve_constraints",
                {
                    "task_description": "Build REST API with FastAPI and Pydantic validation",
                    "libraries": ["fastapi", "pydantic", "sqlalchemy"],
                    "project_dir": fixture_dir
                }
            )
            resolve_text = res_resolve.content[0].text
            print("=== EXACT resolve_constraints OUTPUT ===")
            print(resolve_text)
            resolve_dict = json.loads(resolve_text)
            resolve_model = ResolvedConstraints.model_validate(resolve_dict)
            assert len(resolve_model.deprecated_patterns) > 0
            assert len(resolve_model.evidence_sources) > 0
            results["resolve_constraints"] = "PASS"
            print(">>> resolve_constraints: PASS (Matches ResolvedConstraints schema)")

            print(f"\n[STEP 4, 5, 6] Executing freshness_audit against '{fixture_dir}' with sample code...")
            sample_audit_code = "from pydantic import BaseModel\nm = BaseModel()\nd = m.dict()"
            res_audit = await session.call_tool("freshness_audit", {"code": sample_audit_code, "project_dir": fixture_dir})
            audit_text = res_audit.content[0].text
            print("=== EXACT freshness_audit OUTPUT ===")
            print(audit_text)
            audit_dict = json.loads(audit_text)
            audit_model = FreshnessAuditReport.model_validate(audit_dict)
            assert not audit_model.clean
            results["freshness_audit"] = "PASS"
            print(">>> freshness_audit: PASS (Matches FreshnessAuditReport schema)")

            # Step 7 & 8: Test freshness_audit with intentionally outdated Pydantic code
            print("\n[STEP 7 & 8] Testing freshness_audit with intentionally outdated Pydantic code...")
            outdated_code = '''from pydantic import BaseModel, validator

class User(BaseModel):
    email: str

    @validator("email")
    def validate_email(cls, value):
        return value
'''
            print("Target Code:")
            print(outdated_code)
            res_outdated = await session.call_tool("freshness_audit", {"code": outdated_code, "project_dir": fixture_dir})
            outdated_text = res_outdated.content[0].text
            print("=== EXACT freshness_audit OUTDATED CODE OUTPUT ===")
            print(outdated_text)
            outdated_dict = json.loads(outdated_text)
            outdated_model = FreshnessAuditReport.model_validate(outdated_dict)
            detected_patterns = [v.detected_pattern for v in outdated_model.violations]
            print(f"Detected patterns: {detected_patterns}")
            assert not outdated_model.clean
            assert any("@validator" in p for p in detected_patterns)
            assert any("validator" in p for p in detected_patterns)
            results["deprecated_code_detection"] = "PASS"
            print(">>> deprecated-code detection: PASS")

            # Step 9: Test freshness_audit with modern equivalent (verify NO false positives)
            print("\n[STEP 9] Testing freshness_audit with modern equivalent code...")
            modern_code = '''from pydantic import BaseModel, field_validator

class User(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return value
'''
            print("Modern Code:")
            print(modern_code)
            res_modern = await session.call_tool("freshness_audit", {"code": modern_code, "project_dir": fixture_dir})
            modern_text = res_modern.content[0].text
            print("=== EXACT freshness_audit MODERN CODE OUTPUT ===")
            print(modern_text)
            modern_dict = json.loads(modern_text)
            modern_model = FreshnessAuditReport.model_validate(modern_dict)
            assert modern_model.clean is True
            assert modern_model.violations_count == 0
            assert len(modern_model.violations) == 0
            results["modern_code_false_positive_test"] = "PASS"
            print(">>> modern-code false-positive test: PASS")

            # Step 10 & 11: Test resolve_constraints for FastAPI + Pydantic with intent
            print("\n[STEP 10 & 11] Testing resolve_constraints for FastAPI + Pydantic...")
            intent = "Add request validation to a FastAPI endpoint"
            print(f"Task Intent: '{intent}'")
            print(f"Libraries: ['fastapi', 'pydantic']")
            res_intent = await session.call_tool(
                "resolve_constraints",
                {
                    "task_description": intent,
                    "libraries": ["fastapi", "pydantic"],
                    "project_dir": fixture_dir
                }
            )
            intent_text = res_intent.content[0].text
            print("=== EXACT resolve_constraints INTENT OUTPUT ===")
            print(intent_text)
            intent_dict = json.loads(intent_text)
            intent_model = ResolvedConstraints.model_validate(intent_dict)
            assert len(intent_model.evidence_sources) > 0

            print("\n=== EVIDENCE / PROVENANCE RETURNED ===")
            for idx, ev in enumerate(intent_model.evidence_sources, 1):
                print(f"[{idx}] Source Type: {ev.source_type}")
                print(f"    Title: {ev.title}")
                print(f"    URL: {ev.url}")
                print(f"    Details: {ev.details}")
                print(f"    Verified At: {ev.verified_at}")

            # Verify evidence has authoritative URLs
            has_official_doc = any(
                ev.url and ("tiangolo.com" in ev.url or "pydantic.dev" in ev.url)
                for ev in intent_model.evidence_sources
            )
            assert has_official_doc
            results["evidence_provenance"] = "PASS"
            print(">>> evidence/provenance: PASS")

    print("\n" + "=" * 80)
    print("FINAL SUMMARY REPORT:")
    print("=" * 80)
    for k, v in results.items():
        print(f"- {k.replace('_', ' ')}: {v}")


if __name__ == "__main__":
    asyncio.run(run_validation())
