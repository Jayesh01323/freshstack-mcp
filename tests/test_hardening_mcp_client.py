"""Hardening Test 1: Real External MCP Client Compatibility.

Simulates an independent, third-party MCP client interacting directly with
FreshStack MCP over standard JSON-RPC 2.0 stdio protocol.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
import pytest


@pytest.mark.asyncio
async def test_external_mcp_client_full_lifecycle():
    """Verify that an external third-party client can perform full MCP protocol negotiation,

    tool discovery, schema validation, tool invocations, and clean shutdown.
    """
    python_bin = sys.executable
    server_module = "freshstack.server"

    # Spawn MCP server subprocess with unbuffered stdio
    proc = await asyncio.create_subprocess_exec(
        python_bin,
        "-u",
        "-m",
        server_module,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "PYTHONUNBUFFERED": "1"}
    )

    req_id = 1

    async def send_rpc(method: str, params: dict = None) -> dict:
        nonlocal req_id
        current_id = req_id
        req_id += 1
        msg = {
            "jsonrpc": "2.0",
            "id": current_id,
            "method": method,
        }
        if params is not None:
            msg["params"] = params

        raw_line = json.dumps(msg) + "\n"
        proc.stdin.write(raw_line.encode())
        await proc.stdin.drain()

        # Read lines until matching response
        while True:
            line = await proc.stdout.readline()
            if not line:
                stderr_data = await proc.stderr.read()
                raise RuntimeError(f"Server closed stream unexpectedly. Stderr: {stderr_data.decode()}")
            line_str = line.decode().strip()
            if not line_str:
                continue
            try:
                data = json.loads(line_str)
                if data.get("id") == current_id:
                    return data
            except json.JSONDecodeError:
                continue

    async def send_notification(method: str, params: dict = None):
        msg = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            msg["params"] = params
        raw_line = json.dumps(msg) + "\n"
        proc.stdin.write(raw_line.encode())
        await proc.stdin.drain()

    try:
        # 1. MCP Initialization & Protocol Negotiation
        init_res = await send_rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "roots": {"listChanged": True},
                "sampling": {}
            },
            "clientInfo": {
                "name": "third-party-external-client",
                "version": "1.0.0"
            }
        })

        assert "result" in init_res, f"Initialization failed: {init_res}"
        result = init_res["result"]
        assert "serverInfo" in result
        assert result["serverInfo"]["name"] == "freshstack-mcp"
        assert "protocolVersion" in result
        assert "capabilities" in result
        assert "tools" in result["capabilities"]

        # Complete handshake with initialized notification
        await send_notification("notifications/initialized")

        # 2. Tool Discovery & JSON Schema Validation
        tools_res = await send_rpc("tools/list")
        assert "result" in tools_res
        tools = tools_res["result"].get("tools", [])
        assert len(tools) == 3

        tool_map = {t["name"]: t for t in tools}
        assert "inspect_stack" in tool_map
        assert "resolve_constraints" in tool_map
        assert "freshness_audit" in tool_map

        # Verify JSON Schema correctness for all tools
        for tool_name, tool in tool_map.items():
            schema = tool.get("inputSchema", {})
            assert schema.get("type") == "object", f"{tool_name} inputSchema must be type object"
            assert "properties" in schema, f"{tool_name} inputSchema must define properties"

        # Check inspect_stack schema
        inspect_schema = tool_map["inspect_stack"]["inputSchema"]
        assert "project_dir" in inspect_schema["properties"]

        # Check resolve_constraints schema
        resolve_schema = tool_map["resolve_constraints"]["inputSchema"]
        assert "task_description" in resolve_schema["properties"]
        assert "task_description" in resolve_schema.get("required", [])

        # Check freshness_audit schema
        audit_schema = tool_map["freshness_audit"]["inputSchema"]
        assert "code" in audit_schema["properties"]
        assert "code" in audit_schema.get("required", [])

        # 3. inspect_stack Invocation
        sample_dir = str(Path(__file__).parent / "fixtures" / "sample_uv")
        call_inspect = await send_rpc("tools/call", {
            "name": "inspect_stack",
            "arguments": {"project_dir": sample_dir}
        })
        assert "result" in call_inspect
        inspect_content = call_inspect["result"]["content"][0]["text"]
        inspect_data = json.loads(inspect_content)
        assert inspect_data["package_manager"] == "uv"
        assert "fastapi" in inspect_data["supported_libraries"]
        assert "pydantic" in inspect_data["supported_libraries"]

        # 4. resolve_constraints Invocation
        call_resolve = await send_rpc("tools/call", {
            "name": "resolve_constraints",
            "arguments": {
                "task_description": "Build user auth API",
                "libraries": ["fastapi", "pydantic"],
                "project_dir": sample_dir
            }
        })
        assert "result" in call_resolve
        resolve_content = call_resolve["result"]["content"][0]["text"]
        resolve_data = json.loads(resolve_content)
        assert resolve_data["confidence"] in ("VERIFIED", "INFERRED")
        assert len(resolve_data["deprecated_patterns"]) > 0
        assert len(resolve_data["evidence_sources"]) > 0

        # 5. freshness_audit Invocation
        code_to_audit = (
            "from pydantic import BaseModel, validator\n"
            "class User(BaseModel):\n"
            "    name: str\n"
            "    @validator('name')\n"
            "    def check_name(cls, v):\n"
            "        return v\n"
        )
        call_audit = await send_rpc("tools/call", {
            "name": "freshness_audit",
            "arguments": {
                "code": code_to_audit,
                "project_dir": sample_dir
            }
        })
        assert "result" in call_audit
        audit_content = call_audit["result"]["content"][0]["text"]
        audit_data = json.loads(audit_content)
        assert audit_data["clean"] is False
        assert audit_data["violations_count"] >= 2
        detected_patterns = [v["detected_pattern"] for v in audit_data["violations"]]
        assert "@validator(...)" in detected_patterns

    finally:
        # 6. Clean Shutdown
        if proc.stdin:
            proc.stdin.close()
            await proc.stdin.wait_closed()
        try:
            await asyncio.wait_for(proc.wait(), timeout=3.0)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
