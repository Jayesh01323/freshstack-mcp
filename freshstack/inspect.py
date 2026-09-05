"""Project dependency and stack inspection for FreshStack MCP."""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Use tomli for Python < 3.11, standard tomllib for 3.11+
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from freshstack.config import logger
from freshstack.models import (
    EvidenceSource,
    ProjectDependency,
    SourceType,
    StackInfo,
)

SUPPORTED_PACKAGES: Set[str] = {
    "fastapi",
    "pydantic",
    "sqlalchemy",
    "alembic",
}


class StackInspector:
    """Inspects project files to determine Python version, package manager, and resolved dependency versions."""

    def __init__(self, project_dir: str = "."):
        self.project_path = Path(project_dir).resolve()

    def inspect(self) -> StackInfo:
        """Run full stack inspection across recognized manifest and lock files."""
        detected_files: List[str] = []
        dependencies: Dict[str, ProjectDependency] = {}
        evidence: List[EvidenceSource] = []
        project_name: Optional[str] = None
        python_version: Optional[str] = None
        package_manager = "pip"

        # 1. Inspect uv.lock (Highest priority for resolved versions and uv package manager)
        uv_lock_path = self.project_path / "uv.lock"
        if uv_lock_path.is_file():
            detected_files.append("uv.lock")
            package_manager = "uv"
            lock_deps, lock_py, lock_evidence = self._parse_uv_lock(uv_lock_path)
            for name, dep in lock_deps.items():
                dependencies[name] = dep
            if lock_py:
                python_version = lock_py
            evidence.extend(lock_evidence)

        # 2. Inspect pyproject.toml
        pyproject_path = self.project_path / "pyproject.toml"
        if pyproject_path.is_file():
            detected_files.append("pyproject.toml")
            p_name, p_py, p_deps, p_pm, p_evidence = self._parse_pyproject(pyproject_path)
            if p_name and not project_name:
                project_name = p_name
            if p_py and not python_version:
                python_version = p_py
            if p_pm and package_manager == "pip":
                package_manager = p_pm

            # Add dependencies from pyproject if not already resolved with exact version
            for name, dep in p_deps.items():
                if name not in dependencies or dependencies[name].resolved_version is None:
                    dependencies[name] = dep
            evidence.extend(p_evidence)

        # 3. Inspect requirements.txt (Standard pip manifest)
        req_path = self.project_path / "requirements.txt"
        if req_path.is_file():
            detected_files.append("requirements.txt")
            req_deps, req_evidence = self._parse_requirements(req_path)
            for name, dep in req_deps.items():
                # Lockfiles take precedence, but pinned requirements.txt overrides open constraints
                if name not in dependencies or (
                    dependencies[name].resolved_version is None and dep.resolved_version is not None
                ):
                    dependencies[name] = dep
            evidence.extend(req_evidence)

        # Extract supported MVP libraries with resolved versions
        supported_libraries: Dict[str, Optional[str]] = {}
        for lib in SUPPORTED_PACKAGES:
            if lib in dependencies:
                supported_libraries[lib] = dependencies[lib].resolved_version

        # Fallback python version if not specified in manifests
        if not python_version:
            python_version = f">={sys.version_info.major}.{sys.version_info.minor}"
            evidence.append(
                EvidenceSource(
                    source_type=SourceType.PROJECT_FILE,
                    title="System Runtime Fallback",
                    details=f"Inferred Python version {python_version} from execution runtime"
                )
            )

        return StackInfo(
            project_name=project_name,
            python_version=python_version,
            package_manager=package_manager,
            detected_files=detected_files,
            dependencies=dependencies,
            supported_libraries=supported_libraries,
            evidence=evidence,
        )

    def _parse_uv_lock(self, path: Path) -> Tuple[Dict[str, ProjectDependency], Optional[str], List[EvidenceSource]]:
        dependencies: Dict[str, ProjectDependency] = {}
        evidence: List[EvidenceSource] = []
        python_version: Optional[str] = None

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            # Extract packages list
            packages = data.get("package", [])
            for pkg in packages:
                raw_name = pkg.get("name")
                version = pkg.get("version")
                if raw_name:
                    canonical = canonicalize_name(raw_name)
                    dependencies[canonical] = ProjectDependency(
                        name=canonical,
                        specifier=f"=={version}" if version else None,
                        resolved_version=version,
                        source_file="uv.lock"
                    )

            evidence.append(
                EvidenceSource(
                    source_type=SourceType.PROJECT_FILE,
                    title="uv.lock Resolution",
                    details=f"Extracted {len(packages)} pinned dependencies from uv.lock"
                )
            )
        except Exception as e:
            logger.warning(f"Error parsing uv.lock: {e}")

        return dependencies, python_version, evidence

    def _parse_pyproject(
        self, path: Path
    ) -> Tuple[Optional[str], Optional[str], Dict[str, ProjectDependency], Optional[str], List[EvidenceSource]]:
        dependencies: Dict[str, ProjectDependency] = {}
        evidence: List[EvidenceSource] = []
        project_name: Optional[str] = None
        python_version: Optional[str] = None
        package_manager: Optional[str] = None

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)

            # Check for uv configuration
            tool_table = data.get("tool", {})
            if "uv" in tool_table:
                package_manager = "uv"
            elif "poetry" in tool_table:
                package_manager = "poetry"

            # PEP 621 metadata
            project = data.get("project", {})
            project_name = project.get("name")
            python_version = project.get("requires-python")

            # PEP 621 dependencies
            pep621_deps = project.get("dependencies", [])
            for dep_str in pep621_deps:
                try:
                    req = Requirement(dep_str)
                    canonical = canonicalize_name(req.name)
                    spec_str = str(req.specifier) if req.specifier else None
                    # If pinned with ==, record as resolved
                    pinned = None
                    if req.specifier:
                        for spec in req.specifier:
                            if spec.operator == "==":
                                pinned = spec.version
                    dependencies[canonical] = ProjectDependency(
                        name=canonical,
                        specifier=spec_str,
                        resolved_version=pinned,
                        source_file="pyproject.toml"
                    )
                except Exception as ex:
                    logger.debug(f"Skipping unparseable dependency '{dep_str}': {ex}")

            # Poetry dependencies fallback
            if "poetry" in tool_table:
                poetry_deps = tool_table["poetry"].get("dependencies", {})
                for raw_name, val in poetry_deps.items():
                    if raw_name.lower() == "python":
                        if not python_version and isinstance(val, str):
                            python_version = val
                        continue
                    canonical = canonicalize_name(raw_name)
                    spec_str = val if isinstance(val, str) else None
                    pinned = val.lstrip("=") if isinstance(val, str) and val.startswith("==") else None
                    dependencies[canonical] = ProjectDependency(
                        name=canonical,
                        specifier=spec_str,
                        resolved_version=pinned,
                        source_file="pyproject.toml (poetry)"
                    )

            evidence.append(
                EvidenceSource(
                    source_type=SourceType.PROJECT_FILE,
                    title="pyproject.toml Manifest",
                    details=f"Parsed project metadata for '{project_name or 'unnamed'}'"
                )
            )
        except Exception as e:
            logger.warning(f"Error parsing pyproject.toml: {e}")

        return project_name, python_version, dependencies, package_manager, evidence

    def _parse_requirements(self, path: Path) -> Tuple[Dict[str, ProjectDependency], List[EvidenceSource]]:
        dependencies: Dict[str, ProjectDependency] = {}
        evidence: List[EvidenceSource] = []

        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines:
                cleaned = line.strip()
                # Skip comments and flags like -r, -i
                if not cleaned or cleaned.startswith("#") or cleaned.startswith("-"):
                    continue
                # Strip inline comments
                if " #" in cleaned:
                    cleaned = cleaned.split(" #", 1)[0].strip()

                try:
                    req = Requirement(cleaned)
                    canonical = canonicalize_name(req.name)
                    spec_str = str(req.specifier) if req.specifier else None
                    pinned = None
                    if req.specifier:
                        for spec in req.specifier:
                            if spec.operator == "==":
                                pinned = spec.version
                    dependencies[canonical] = ProjectDependency(
                        name=canonical,
                        specifier=spec_str,
                        resolved_version=pinned,
                        source_file="requirements.txt"
                    )
                except Exception as ex:
                    # Basic regex fallback for simple requirements lines
                    match = re.match(r"^([a-zA-Z0-9_\-\.]+)\s*(==|>=|<=|~=|>|<)\s*([a-zA-Z0-9_\-\.]+)", cleaned)
                    if match:
                        raw_name, op, ver = match.groups()
                        canonical = canonicalize_name(raw_name)
                        dependencies[canonical] = ProjectDependency(
                            name=canonical,
                            specifier=f"{op}{ver}",
                            resolved_version=ver if op == "==" else None,
                            source_file="requirements.txt"
                        )
                    else:
                        logger.debug(f"Could not parse requirements line '{cleaned}': {ex}")

            evidence.append(
                EvidenceSource(
                    source_type=SourceType.PROJECT_FILE,
                    title="requirements.txt Manifest",
                    details=f"Extracted {len(dependencies)} dependencies from requirements.txt"
                )
            )
        except Exception as e:
            logger.warning(f"Error parsing requirements.txt: {e}")

        return dependencies, evidence


def inspect_stack(project_dir: str = ".") -> StackInfo:
    """Convenience entry point for inspecting project stack."""
    return StackInspector(project_dir).inspect()
