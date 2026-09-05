# FreshStack MCP

> **Evidence-backed technology intelligence layer for AI coding agents.**  
> Prevents AI coding assistants from generating outdated, deprecated, or version-incompatible code.

---

## The Problem

AI coding assistants frequently generate code using outdated syntax, deprecated methods, or incompatible library versions because their parametric memory lacks real-time awareness of:
1. The project's actual, resolved dependency versions in lockfiles.
2. Official deprecation cycles and migration guides (e.g., Pydantic v1 vs. v2, SQLAlchemy 1.4 vs. 2.0, FastAPI lifespan vs. `@app.on_event`).
3. Exact version compatibility boundaries.

## Core Principle: Evidence Priority

**FreshStack does NOT guess or decide what is "modern" from parametric memory.**

It verifies technology information strictly against authoritative sources according to an explicit hierarchy:

1. **Actual project state and resolved dependency versions** (`uv.lock`, pinned `requirements.txt`, `pyproject.toml`)
2. **Official version-specific documentation**
3. **Official migration guides**
4. **Official changelogs**
5. **Official package registry metadata (PyPI)**
6. **Other authoritative sources**
7. **LLM knowledge only when no stronger evidence exists**

> **The Golden Rule**: The project's resolved dependency version has absolute priority over the latest available package version. If a project is pinned to FastAPI `0.115.x`, FreshStack never blindly enforces documentation from an incompatible newer release.

---

## MVP Scope (Python)

### Supported Project Manifests & Lockfiles
- `uv.lock`
- `pyproject.toml` (PEP 621 & Poetry)
- `requirements.txt`

### Supported Target Packages
- **FastAPI** (Lifespan handlers, Pydantic v2 schemas)
- **Pydantic** (`model_dump`, `model_validate`, `model_config = ConfigDict`, `@field_validator`, `@model_validator`)
- **SQLAlchemy** (2.0 style queries, `DeclarativeBase`, `mapped_column`, `session.execute(select(...))`)
- **Alembic** (1.12+ connection context migrations)

---

## Architecture & Module Structure

```
freshstack-mcp/
├── freshstack/
│   ├── __init__.py          # Package entry and version
│   ├── config.py            # Environment variables, logging, cache path configuration
│   ├── models.py            # Pydantic v2 schemas (StackInfo, EvidenceSource, AuditViolation)
│   ├── cache.py             # Local SQLite database abstraction with TTL
│   ├── inspect.py           # Stack inspection (uv.lock, pyproject.toml, requirements.txt)
│   ├── pypi.py              # PyPI registry metadata client with local caching
│   ├── knowledge.py         # Authoritative version rules & official documentation citations
│   ├── resolve.py           # Constraint resolution pipeline (VERIFIED, INFERRED, UNKNOWN)
│   ├── audit.py             # Deterministic AST static analysis and violation detection
│   └── server.py            # FastMCP / MCPServer stdio transport server
├── tests/
│   ├── fixtures/            # Sample lockfiles and manifests (uv.lock, pyproject.toml, requirements.txt)
│   ├── test_inspect.py      # Stack inspection unit tests
│   ├── test_cache.py        # SQLite cache and TTL tests
│   ├── test_resolve.py      # Constraint resolution and priority tests
│   ├── test_audit.py        # Deterministic AST audit tests
│   └── test_server.py       # MCP server tool execution tests
├── pyproject.toml           # Modern PEP 621 configuration (uv-compatible)
├── CONTRIBUTING.md          # Development and contribution standards
├── LICENSE                  # MIT License
├── .env.example             # Configuration templates
└── .gitignore               # Clean source control patterns
```

---

## MCP Capabilities & Tools

### 1. `inspect_stack(project_dir: str = ".") -> str`
Detects project metadata, Python version, package manager (`uv`, `poetry`, `pip`), and exact resolved versions for all supported libraries.

**Example Response:**
```json
{
  "project_name": "sample-service",
  "python_version": ">=3.10",
  "package_manager": "uv",
  "detected_files": ["uv.lock", "pyproject.toml"],
  "supported_libraries": {
    "fastapi": "0.115.0",
    "pydantic": "2.9.2",
    "sqlalchemy": "2.0.35",
    "alembic": "1.13.3"
  }
}
```

### 2. `resolve_constraints(task_description: str, libraries: list = None, project_dir: str = ".") -> str`
Given a developer task and target libraries, determines active version constraints, deprecated APIs, recommended replacements, and authoritative evidence citations.

**Example Output (excerpt):**
```json
{
  "confidence": "VERIFIED",
  "deprecated_patterns": [
    {
      "name": "BaseModel.dict()",
      "status": "deprecated",
      "reason": ".dict() is deprecated in Pydantic v2. Use .model_dump() instead.",
      "replacement": "model.model_dump(mode='python')",
      "evidence": {
        "source_type": "migration_guide",
        "title": "Pydantic V2 Migration Guide - Model Methods",
        "url": "https://docs.pydantic.dev/latest/migration/#changes-to-pydanticbasemodel"
      }
    }
  ]
}
```

### 3. `freshness_audit(code: str, project_dir: str = ".") -> str`
Analyzes generated or developer-written Python code using deterministic static AST analysis. Pinpoints exact line numbers, columns, severity, rationale, and authoritative evidence for deprecated or incompatible APIs.

---

## Local-First Privacy Guarantee

FreshStack is designed with privacy as a foundational requirement:
- **Local AST Analysis**: Code parsing occurs on the local machine via Python's `ast` module.
- **No Secret Transmission**: API keys, passwords, environment variables, and unrelated codebase files are never transmitted externally.
- **Offline Capable**: Operates seamlessly in offline environments using the local SQLite evidence cache.

---

## Getting Started

### Installation

Clone the repository and install with `uv`:

```bash
git clone https://github.com/freshstack/freshstack-mcp.git
cd freshstack-mcp

# Create virtual environment and install
uv venv .venv
uv pip install -e ".[dev]"
```

### Running the MCP Server

Start the server using stdio transport:

```bash
uv run freshstack
```

Or run via Python directly:

```bash
python -m freshstack.server
```

### Integrating with Claude Desktop / Cursor

Add FreshStack to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "freshstack": {
      "command": "uv",
      "args": [
        "--directory",
        "/path/to/freshstack-mcp",
        "run",
        "freshstack"
      ]
    }
  }
}
```

### Running Tests

Execute the complete test suite:

```bash
uv run pytest -v
```
