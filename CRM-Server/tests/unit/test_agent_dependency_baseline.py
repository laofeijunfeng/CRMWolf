from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from scripts.verify_agent_dependency_baseline import (
    DEVELOPMENT_PACKAGES,
    load_development_dependency_baseline,
    load_development_requirements_baseline,
)


def test_development_dependency_sources_have_the_same_exact_pins() -> None:
    pyproject_baseline = load_development_dependency_baseline()
    requirements_baseline = load_development_requirements_baseline()

    assert pyproject_baseline == requirements_baseline
    assert pyproject_baseline.keys() == DEVELOPMENT_PACKAGES


def test_development_dependency_baseline_rejects_range_pins(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        """
[project]
name = "test"
version = "0.0.0"
[project.optional-dependencies]
dev = [
  "pytest>=9",
  "pytest-asyncio==1.4.0",
  "pytest-cov==7.1.0",
  "ruff==0.16.4",
  "mypy==2.3.1",
  "types-redis==4.6.0.20241004",
]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="must exactly pin pytest with =="):
        load_development_dependency_baseline(pyproject)
