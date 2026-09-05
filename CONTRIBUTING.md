# Contributing to FreshStack MCP

Thank you for your interest in contributing to FreshStack MCP!

FreshStack MCP is an evidence-backed technology intelligence layer for AI coding agents. Its purpose is to prevent AI coding assistants from generating outdated, deprecated, or version-incompatible code.

## Core Principles

1. **Evidence Priority**: FreshStack does NOT guess or decide what is "modern" from memory. It verifies against authoritative sources:
   - Resolved project dependencies
   - Official version-specific documentation
   - Official migration guides & changelogs
   - Official package registry metadata (PyPI)
2. **Local-First & Privacy-Focused**: Never expose secrets, credentials, or unrelated source code.
3. **Deterministic First**: Prefer static AST analysis and verified rules over speculative LLM reasoning.

## Development Setup

We use `uv` for fast, reproducible Python dependency management:

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv .venv
uv pip install -e ".[dev]"
```

## Running Tests

Run the test suite using `pytest`:

```bash
uv run pytest
```

## Project Standards

- Strict typing with modern Python 3.10+ syntax.
- Modern Pydantic v2 (never use deprecated Pydantic v1 APIs).
- Clean error handling with informative, actionable messages.
- New rules or detectors must include evidence sources (URLs, release dates, versions).
