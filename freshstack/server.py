"""Model Context Protocol (MCP) Server for FreshStack."""

import json
import sys
from typing import Any, Dict, List, Optional, Union

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from freshstack.audit import freshness_audit as run_audit
from freshstack.config import logger
from freshstack.inspect import inspect_stack as run_inspect
from freshstack.resolve import resolve_constraints as run_resolve

server = MCPServer(
    name="freshstack-mcp",
    instructions=(
        "FreshStack MCP provides evidence-backed technology intelligence for Python projects. "
        "It verifies API freshness, deprecations, and compatibility strictly against resolved "
        "project versions and authoritative official documentation."
    )
)


@server.tool()
def inspect_stack(project_dir: str = ".") -> str:
    """Detect Python version, package manager, resolved dependencies, and supported libraries.

    Args:
        project_dir: Root directory of the Python project to inspect (defaults to current directory).

    Returns:
        JSON string containing StackInfo with resolved versions and evidence sources.
    """
    logger.info(f"Tool call: inspect_stack(project_dir='{project_dir}')")
    try:
        stack = run_inspect(project_dir)
        return json.dumps(stack.model_dump(mode="json"), indent=2)
    except Exception as e:
        logger.error(f"Error in inspect_stack: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


@server.tool()
def resolve_constraints(
    task_description: str,
    libraries: Optional[Union[List[str], Dict[str, Optional[str]]]] = None,
    project_dir: str = "."
) -> str:
    """Determine exact project dependency versions and retrieve authoritative version-specific constraints.

    Identifies version-specific APIs, deprecated/forbidden patterns, recommended patterns,
    and authoritative evidence sources (documentation URLs, changelogs).

    Args:
        task_description: Description of the coding task or feature to implement.
        libraries: Optional list or mapping of specific libraries to inspect (e.g. ['fastapi', 'pydantic']).
        project_dir: Root directory of the Python project (defaults to current directory).

    Returns:
        JSON string containing ResolvedConstraints with verified rules and evidence.
    """
    logger.info(f"Tool call: resolve_constraints(task='{task_description}')")
    try:
        constraints = run_resolve(task_description, libraries=libraries, project_dir=project_dir)
        return json.dumps(constraints.model_dump(mode="json"), indent=2)
    except Exception as e:
        logger.error(f"Error in resolve_constraints: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


@server.tool()
def freshness_audit(code: str, project_dir: str = ".") -> str:
    """Analyze Python code to detect deprecated APIs, version mismatches, and outdated patterns.

    Uses deterministic static AST analysis grounded in authoritative documentation.

    Args:
        code: Python source code snippet or module to audit.
        project_dir: Root directory of the Python project to ground version context against.

    Returns:
        JSON string containing FreshnessAuditReport with detected violations, severity, and replacements.
    """
    logger.info(f"Tool call: freshness_audit(code_length={len(code)})")
    try:
        report = run_audit(code, project_dir=project_dir)
        return json.dumps(report.model_dump(mode="json"), indent=2)
    except Exception as e:
        logger.error(f"Error in freshness_audit: {e}")
        return json.dumps({"error": str(e), "status": "failed"})


def main():
    """Run the FreshStack MCP server over stdio."""
    logger.info("Starting FreshStack MCP server on stdio transport...")
    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        logger.info("FreshStack MCP server stopped.")
    except Exception as e:
        logger.critical(f"FreshStack MCP server fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
