"""Deterministic static AST analysis and freshness auditing for Python code."""

import ast
from typing import List, Optional, Set

from freshstack.config import logger
from freshstack.inspect import StackInspector
from freshstack.knowledge import get_rules_for_package
from freshstack.models import (
    AuditViolation,
    Confidence,
    EvidenceSource,
    FreshnessAuditReport,
    Severity,
    SourceType,
    StackInfo,
)


class ContextCollector(ast.NodeVisitor):
    """Pre-scans AST to collect import and class context for accurate attribution."""

    def __init__(self):
        self.imported_modules: Set[str] = set()
        self.pydantic_symbols: Dict[str, str] = {}
        self.sqlalchemy_symbols: Dict[str, str] = {}
        self.fastapi_symbols: Dict[str, str] = {}
        self.pydantic_model_classes: Set[str] = set()
        self.unrelated_classes: Set[str] = set()
        self.unrelated_instances: Set[str] = set()
        self.pydantic_instances: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            mod_root = alias.name.split(".")[0]
            self.imported_modules.add(mod_root)
            if mod_root == "pydantic":
                self.pydantic_symbols[alias.asname or alias.name] = "pydantic"
            elif mod_root == "sqlalchemy":
                self.sqlalchemy_symbols[alias.asname or alias.name] = "sqlalchemy"
            elif mod_root == "fastapi":
                self.fastapi_symbols[alias.asname or alias.name] = "fastapi"
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        mod_root = mod.split(".")[0]
        self.imported_modules.add(mod_root)
        if mod == "pydantic" or mod.startswith("pydantic."):
            for alias in node.names:
                self.pydantic_symbols[alias.asname or alias.name] = alias.name
        elif mod == "sqlalchemy" or mod.startswith("sqlalchemy."):
            for alias in node.names:
                self.sqlalchemy_symbols[alias.asname or alias.name] = alias.name
        elif mod == "fastapi" or mod.startswith("fastapi."):
            for alias in node.names:
                self.fastapi_symbols[alias.asname or alias.name] = alias.name
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        is_pydantic = False
        for base in node.bases:
            if isinstance(base, ast.Name):
                if base.id in ("BaseModel", "BaseSettings") or base.id in self.pydantic_model_classes:
                    is_pydantic = True
                elif self.pydantic_symbols.get(base.id) in ("BaseModel", "BaseSettings"):
                    is_pydantic = True
            elif isinstance(base, ast.Attribute):
                if base.attr in ("BaseModel", "BaseSettings"):
                    is_pydantic = True
        if is_pydantic:
            self.pydantic_model_classes.add(node.name)
        else:
            self.unrelated_classes.add(node.name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if isinstance(node.value, ast.Call):
            call_func = node.value.func
            if isinstance(call_func, ast.Name):
                if call_func.id in self.unrelated_classes:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.unrelated_instances.add(target.id)
                elif call_func.id in self.pydantic_model_classes or call_func.id == "BaseModel":
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            self.pydantic_instances.add(target.id)
        self.generic_visit(node)


class FreshnessASTVisitor(ast.NodeVisitor):
    """AST Visitor that deterministically flags deprecated or incompatible patterns."""

    def __init__(
        self,
        pydantic_version: Optional[str] = None,
        sqlalchemy_version: Optional[str] = None,
        fastapi_version: Optional[str] = None,
        context: Optional[ContextCollector] = None
    ):
        self.pydantic_version = pydantic_version
        self.sqlalchemy_version = sqlalchemy_version
        self.fastapi_version = fastapi_version
        self.ctx = context or ContextCollector()

        self.violations: List[AuditViolation] = []
        self.analyzed_packages: Set[str] = set()

        # Cache rules
        self.pydantic_rules = {r.api_name: r for r in get_rules_for_package("pydantic", pydantic_version)}
        self.fastapi_rules = {r.api_name: r for r in get_rules_for_package("fastapi", fastapi_version)}
        self.sqlalchemy_rules = {r.api_name: r for r in get_rules_for_package("sqlalchemy", sqlalchemy_version)}

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Inspect imports for deprecated modules or symbols."""
        module = node.module or ""

        if module == "pydantic" or module.startswith("pydantic."):
            self.analyzed_packages.add("pydantic")
            for alias in node.names:
                if alias.name in ("validator", "root_validator"):
                    rule = self.pydantic_rules.get(f"@{alias.name}")
                    if rule:
                        self.violations.append(
                            AuditViolation(
                                severity=Severity.WARNING,
                                package="pydantic",
                                version=self.pydantic_version,
                                detected_pattern=f"from pydantic import {alias.name}",
                                line_number=node.lineno,
                                column=node.col_offset + 1,
                                reason=rule.reason,
                                recommended_replacement=rule.replacement or "Use modern validator decorator",
                                evidence=rule.evidence,
                                confidence=Confidence.VERIFIED
                            )
                        )
                elif alias.name == "BaseSettings":
                    rule = self.pydantic_rules.get("from pydantic import BaseSettings")
                    if rule:
                        self.violations.append(
                            AuditViolation(
                                severity=Severity.ERROR,
                                package="pydantic",
                                version=self.pydantic_version,
                                detected_pattern="from pydantic import BaseSettings",
                                line_number=node.lineno,
                                column=node.col_offset + 1,
                                reason=rule.reason,
                                recommended_replacement=rule.replacement or "from pydantic_settings import BaseSettings",
                                evidence=rule.evidence,
                                confidence=Confidence.VERIFIED
                            )
                        )

        elif "sqlalchemy" in module:
            self.analyzed_packages.add("sqlalchemy")
            if "declarative" in module:
                for alias in node.names:
                    if alias.name == "declarative_base":
                        rule = self.sqlalchemy_rules.get("declarative_base()")
                        if rule:
                            self.violations.append(
                                AuditViolation(
                                    severity=Severity.WARNING,
                                    package="sqlalchemy",
                                    version=self.sqlalchemy_version,
                                    detected_pattern=f"from {module} import declarative_base",
                                    line_number=node.lineno,
                                    column=node.col_offset + 1,
                                    reason=rule.reason,
                                    recommended_replacement="from sqlalchemy.orm import DeclarativeBase; class Base(DeclarativeBase): pass",
                                    evidence=rule.evidence,
                                    confidence=Confidence.VERIFIED
                                )
                            )

        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Inspect class bodies for legacy inner Config classes."""
        is_pydantic = (
            node.name in self.ctx.pydantic_model_classes
            or any(
                (isinstance(b, ast.Name) and (b.id in ("BaseModel", "BaseSettings") or self.ctx.pydantic_symbols.get(b.id) in ("BaseModel", "BaseSettings")))
                or (isinstance(b, ast.Attribute) and b.attr in ("BaseModel", "BaseSettings"))
                for b in node.bases
            )
        )
        if is_pydantic:
            for item in node.body:
                if isinstance(item, ast.ClassDef) and item.name == "Config":
                    self.analyzed_packages.add("pydantic")
                    rule = self.pydantic_rules.get("class Config: inside BaseModel")
                    if rule:
                        self.violations.append(
                            AuditViolation(
                                severity=Severity.WARNING,
                                package="pydantic",
                                version=self.pydantic_version,
                                detected_pattern="class Config:",
                                line_number=item.lineno,
                                column=item.col_offset + 1,
                                reason=rule.reason,
                                recommended_replacement="model_config = ConfigDict(from_attributes=True)",
                                evidence=rule.evidence,
                                confidence=Confidence.VERIFIED
                            )
                        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Inspect decorators on functions (e.g. @app.on_event, @validator)."""
        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Inspect decorators on async functions."""
        self._check_decorators(node.decorator_list)
        self.generic_visit(node)

    def _check_decorators(self, decorator_list: List[ast.expr]) -> None:
        for deco in decorator_list:
            # Check @app.on_event("startup")
            if isinstance(deco, ast.Call):
                func = deco.func
                if isinstance(func, ast.Attribute) and func.attr == "on_event":
                    if "fastapi" in self.ctx.imported_modules or "FastAPI" in self.ctx.fastapi_symbols:
                        self.analyzed_packages.add("fastapi")
                        rule = self.fastapi_rules.get('@app.on_event("startup") / @app.on_event("shutdown")')
                        if rule:
                            self.violations.append(
                                AuditViolation(
                                    severity=Severity.WARNING,
                                    package="fastapi",
                                    version=self.fastapi_version,
                                    detected_pattern="@app.on_event(...)",
                                    line_number=deco.lineno,
                                    column=deco.col_offset + 1,
                                    reason=rule.reason,
                                    recommended_replacement=rule.replacement or "Use lifespan asynccontextmanager",
                                    evidence=rule.evidence,
                                    confidence=Confidence.VERIFIED
                                )
                            )
                elif isinstance(func, ast.Name):
                    if func.id == "validator":
                        if self.ctx.pydantic_symbols.get("validator") == "validator" or "pydantic" in self.ctx.imported_modules:
                            self.analyzed_packages.add("pydantic")
                            rule = self.pydantic_rules.get("@validator")
                            if rule:
                                self.violations.append(
                                    AuditViolation(
                                        severity=Severity.WARNING,
                                        package="pydantic",
                                        version=self.pydantic_version,
                                        detected_pattern="@validator(...)",
                                        line_number=deco.lineno,
                                        column=deco.col_offset + 1,
                                        reason=rule.reason,
                                        recommended_replacement=rule.replacement or "@field_validator",
                                        evidence=rule.evidence,
                                        confidence=Confidence.VERIFIED
                                    )
                                )
                    elif func.id == "root_validator":
                        if self.ctx.pydantic_symbols.get("root_validator") == "root_validator" or "pydantic" in self.ctx.imported_modules:
                            self.analyzed_packages.add("pydantic")
                            rule = self.pydantic_rules.get("@root_validator")
                            if rule:
                                self.violations.append(
                                    AuditViolation(
                                        severity=Severity.WARNING,
                                        package="pydantic",
                                        version=self.pydantic_version,
                                        detected_pattern="@root_validator(...)",
                                        line_number=deco.lineno,
                                        column=deco.col_offset + 1,
                                        reason=rule.reason,
                                        recommended_replacement=rule.replacement or "@model_validator",
                                        evidence=rule.evidence,
                                        confidence=Confidence.VERIFIED
                                    )
                                )

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect function and method calls."""
        # 1. Check Field(regex=...)
        if isinstance(node.func, ast.Name) and node.func.id == "Field":
            if self.ctx.pydantic_symbols.get("Field") == "Field" or "pydantic" in self.ctx.imported_modules:
                for kw in node.keywords:
                    if kw.arg == "regex":
                        self.analyzed_packages.add("pydantic")
                        rule = self.pydantic_rules.get("Field(regex=...)")
                        if rule:
                            self.violations.append(
                                AuditViolation(
                                    severity=Severity.WARNING,
                                    package="pydantic",
                                    version=self.pydantic_version,
                                    detected_pattern="Field(regex=...)",
                                    line_number=node.lineno,
                                    column=node.col_offset + 1,
                                    reason=rule.reason,
                                    recommended_replacement="Field(pattern=...)",
                                    evidence=rule.evidence,
                                    confidence=Confidence.VERIFIED
                                )
                            )

        # 2. Check method calls on models and sessions
        if isinstance(node.func, ast.Attribute):
            attr_name = node.func.attr

            # Pydantic v1 method calls
            if attr_name in ("dict", "parse_obj", "parse_raw"):
                if "pydantic" in self.ctx.imported_modules:
                    caller_id = node.func.value.id if isinstance(node.func.value, ast.Name) else None
                    is_unrelated = caller_id and caller_id in self.ctx.unrelated_instances

                    if not is_unrelated:
                        flag = False
                        if attr_name in ("parse_obj", "parse_raw"):
                            if caller_id and (
                                caller_id in self.ctx.pydantic_model_classes
                                or caller_id == "BaseModel"
                                or caller_id.endswith("Model")
                                or caller_id.endswith("Schema")
                                or caller_id.endswith("Create")
                                or caller_id.endswith("Update")
                            ):
                                flag = True
                        elif attr_name == "dict":
                            if caller_id not in self.ctx.unrelated_classes:
                                flag = True

                        if flag:
                            self.analyzed_packages.add("pydantic")
                            mapping = {
                                "dict": ("BaseModel.dict()", "model.model_dump()"),
                                "parse_obj": ("BaseModel.parse_obj()", "Model.model_validate(obj)"),
                                "parse_raw": ("BaseModel.parse_raw()", "Model.model_validate_json(raw_str)"),
                            }
                            rule_name, repl = mapping[attr_name]
                            rule = self.pydantic_rules.get(rule_name)
                            if rule:
                                self.violations.append(
                                    AuditViolation(
                                        severity=Severity.WARNING,
                                        package="pydantic",
                                        version=self.pydantic_version,
                                        detected_pattern=f".{attr_name}()",
                                        line_number=node.lineno,
                                        column=node.col_offset + 1,
                                        reason=rule.reason,
                                        recommended_replacement=rule.replacement or repl,
                                        evidence=rule.evidence,
                                        confidence=Confidence.VERIFIED
                                    )
                                )

            # SQLAlchemy legacy session.query()
            elif attr_name == "query":
                if "sqlalchemy" in self.ctx.imported_modules and isinstance(node.func.value, ast.Name) and node.func.value.id in ("db", "session", "s"):
                    self.analyzed_packages.add("sqlalchemy")
                    rule = self.sqlalchemy_rules.get("session.query(Model)")
                    if rule:
                        self.violations.append(
                            AuditViolation(
                                severity=Severity.WARNING,
                                package="sqlalchemy",
                                version=self.sqlalchemy_version,
                                detected_pattern=f"{node.func.value.id}.query(...)",
                                line_number=node.lineno,
                                column=node.col_offset + 1,
                                reason=rule.reason,
                                recommended_replacement=rule.replacement or "session.execute(select(Model)).scalars()",
                                evidence=rule.evidence,
                                confidence=Confidence.VERIFIED
                            )
                        )

            # SQLAlchemy engine.execute()
            elif attr_name == "execute":
                if "sqlalchemy" in self.ctx.imported_modules and isinstance(node.func.value, ast.Name) and node.func.value.id in ("engine", "eng"):
                    self.analyzed_packages.add("sqlalchemy")
                    rule = self.sqlalchemy_rules.get("engine.execute('...')")
                    if rule:
                        self.violations.append(
                            AuditViolation(
                                severity=Severity.ERROR,
                                package="sqlalchemy",
                                version=self.sqlalchemy_version,
                                detected_pattern=f"{node.func.value.id}.execute(...)",
                                line_number=node.lineno,
                                column=node.col_offset + 1,
                                reason=rule.reason,
                                recommended_replacement=rule.replacement or "with engine.connect() as conn: conn.execute(...)",
                                evidence=rule.evidence,
                                confidence=Confidence.VERIFIED
                            )
                        )

        self.generic_visit(node)


class FreshnessAuditor:
    """Audits Python code for freshness against authoritative evidence."""

    def __init__(self, project_dir: str = "."):
        self.project_dir = project_dir
        self.inspector = StackInspector(project_dir)

    def audit(self, code: str, stack_info: Optional[StackInfo] = None) -> FreshnessAuditReport:
        """Run freshness audit on Python source code."""
        lines = code.splitlines()
        scanned_lines = len(lines)

        stack = stack_info or self.inspector.inspect()
        pydantic_ver = stack.supported_libraries.get("pydantic")
        sqlalchemy_ver = stack.supported_libraries.get("sqlalchemy")
        fastapi_ver = stack.supported_libraries.get("fastapi")

        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            # Return syntax error as an error violation
            violation = AuditViolation(
                severity=Severity.ERROR,
                package="python",
                version=stack.python_version,
                detected_pattern=f"SyntaxError: {e.msg}",
                line_number=e.lineno,
                column=e.offset,
                reason=f"Python code could not be parsed: {e.msg}",
                recommended_replacement="Fix syntax error before running freshness audit",
                evidence=EvidenceSource(
                    source_type=SourceType.AUTHORITATIVE_SOURCE,
                    title="Python AST Parser",
                    details=f"Code syntax verification failed: {e.msg}"
                ),
                confidence=Confidence.VERIFIED
            )
            return FreshnessAuditReport(
                code_summary=f"Syntax error at line {e.lineno}",
                scanned_lines=scanned_lines,
                violations_count=1,
                violations=[violation],
                analyzed_packages=[],
                clean=False
            )

        collector = ContextCollector()
        collector.visit(tree)

        visitor = FreshnessASTVisitor(
            pydantic_version=pydantic_ver,
            sqlalchemy_version=sqlalchemy_ver,
            fastapi_version=fastapi_ver,
            context=collector
        )
        visitor.visit(tree)

        violations = visitor.violations
        clean = len(violations) == 0
        code_summary = f"Scanned {scanned_lines} lines; found {len(violations)} issue(s)"

        return FreshnessAuditReport(
            code_summary=code_summary,
            scanned_lines=scanned_lines,
            violations_count=len(violations),
            violations=violations,
            analyzed_packages=sorted(list(visitor.analyzed_packages)),
            clean=clean
        )


def freshness_audit(code: str, project_dir: str = ".") -> FreshnessAuditReport:
    """Convenience entry point for auditing code freshness."""
    return FreshnessAuditor(project_dir).audit(code)
