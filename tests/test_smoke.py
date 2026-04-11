"""Smoke tests — verify all pipeline modules parse cleanly.

Real unit + integration tests land in Sprint 5 (US-5.1).
"""

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent

MODULES = [
    "write/generate_seeds_unified.py",
    "write/config/settings.py",
    "write/producers/seed_producer.py",
    "write/consumers/bronze_writer.py",
    "dags/energy_ingestion_dag.py",
]


@pytest.mark.parametrize("path", MODULES)
def test_module_parses(path: str) -> None:
    """Each module must be syntactically valid Python."""
    src = (ROOT / path).read_text()
    ast.parse(src)
