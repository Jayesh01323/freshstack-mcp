"""Hardening Test 5: False-Positive / Adversarial Testing.

Tests that the AST analysis remains precise and resistant to false positives when
encountering code syntax resembling deprecated patterns but belonging to unrelated
classes, modules, standard libraries, or comments/strings.
"""

from freshstack.audit import FreshnessAuditor
from freshstack.models import StackInfo


def test_adversarial_unrelated_class_config():
    """Verify that an inner 'class Config' in a non-Pydantic class is NOT flagged."""
    code = (
        "class NetworkClient:\n"
        "    class Config:\n"
        "        timeout_seconds: int = 30\n"
        "        max_retries: int = 5\n"
        "    def connect(self):\n"
        "        return self.Config.timeout_seconds\n"
    )
    auditor = FreshnessAuditor()
    stack = StackInfo(python_version="3.12", package_manager="uv", supported_libraries={"pydantic": "2.9.2"})
    report = auditor.audit(code, stack_info=stack)
    assert report.clean is True
    assert report.violations_count == 0


def test_adversarial_unrelated_dot_dict_and_parse_obj():
    """Verify that .dict() or .parse_obj() on non-Pydantic models is NOT flagged as a Pydantic violation."""
    code = (
        "class RecordDict:\n"
        "    def __init__(self, data):\n"
        "        self._data = data\n"
        "    def dict(self):\n"
        "        return self._data\n"
        "    def parse_obj(self, raw):\n"
        "        return self._data\n"
        "\n"
        "rec = RecordDict({'key': 'val'})\n"
        "d = rec.dict()\n"
        "p = rec.parse_obj({'key': 'val2'})\n"
    )
    auditor = FreshnessAuditor()
    stack = StackInfo(python_version="3.12", package_manager="uv", supported_libraries={"pydantic": "2.9.2"})
    report = auditor.audit(code, stack_info=stack)
    assert report.clean is True
    assert report.violations_count == 0


def test_adversarial_unrelated_query_method():
    """Verify that a query() call on an Elasticsearch, Prometheus, or custom client without SQLAlchemy is NOT flagged."""
    code = (
        "class MetricStore:\n"
        "    def query(self, promql: str):\n"
        "        return [{'metric': 'cpu', 'value': 42}]\n"
        "\n"
        "store = MetricStore()\n"
        "results = store.query('up{job=\"node\"}')\n"
    )
    auditor = FreshnessAuditor()
    stack = StackInfo(python_version="3.12", package_manager="uv", supported_libraries={"sqlalchemy": "2.0.35"})
    report = auditor.audit(code, stack_info=stack)
    assert report.clean is True
    assert report.violations_count == 0


def test_adversarial_unrelated_validator_decorator():
    """Verify that a custom @validator decorator not imported from Pydantic is NOT flagged."""
    code = (
        "def validator(field_name: str):\n"
        "    def decorator(fn):\n"
        "        return fn\n"
        "    return decorator\n"
        "\n"
        "class FormHandler:\n"
        "    @validator('username')\n"
        "    def validate_name(self, value):\n"
        "        return value.strip()\n"
    )
    auditor = FreshnessAuditor()
    stack = StackInfo(python_version="3.12", package_manager="uv", supported_libraries={"pydantic": "2.9.2"})
    report = auditor.audit(code, stack_info=stack)
    assert report.clean is True
    assert report.violations_count == 0


def test_adversarial_comments_and_docstrings():
    """Verify that mentions of deprecated APIs in comments, docstrings, or string literals

    do not trigger AST false positives.
    """
    code = (
        "'''\n"
        "Architecture Notes:\n"
        "Do NOT use legacy @validator or session.query() in this codebase!\n"
        "Also avoid BaseModel.dict() and BaseModel.parse_obj().\n"
        "'''\n"
        "# Note: replace session.query() with select() queries\n"
        "guide_url = 'https://docs.pydantic.dev/migration/#validators'\n"
        "deprecation_notice = 'The old method was .dict() or class Config:'\n"
    )
    auditor = FreshnessAuditor()
    stack = StackInfo(python_version="3.12", package_manager="uv", supported_libraries={"pydantic": "2.9.2", "sqlalchemy": "2.0.35"})
    report = auditor.audit(code, stack_info=stack)
    assert report.clean is True
    assert report.violations_count == 0
