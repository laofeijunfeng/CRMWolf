#!/usr/bin/env python3
"""Verify exact CRM Agent runtime and optional development dependency baselines."""

from __future__ import annotations

import argparse
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Final

from packaging.requirements import InvalidRequirement, Requirement

PROJECT_ROOT: Final = Path(__file__).parents[1]
PYPROJECT_PATH: Final = PROJECT_ROOT / "pyproject.toml"
REQUIREMENTS_PATH: Final = PROJECT_ROOT / "requirements.txt"
DEV_REQUIREMENTS_PATH: Final = PROJECT_ROOT / "requirements-dev.txt"
AGENT_RUNTIME_PACKAGES: Final[frozenset[str]] = frozenset(
    {
        "langchain",
        "langgraph",
        "langchain-core",
        "langchain-openai",
        "langchain-anthropic",
        "pydantic",
    }
)
DEVELOPMENT_PACKAGES: Final[frozenset[str]] = frozenset(
    {
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "ruff",
        "mypy",
        "types-redis",
    }
)


def _normalize_package_name(name: str) -> str:
    return name.strip().lower().replace("_", "-")


def _load_exact_pins(dependencies: list[object], packages: frozenset[str], source: str) -> dict[str, str]:
    baseline: dict[str, str] = {}
    for dependency in dependencies:
        if not isinstance(dependency, str):
            continue
        try:
            requirement = Requirement(dependency)
        except InvalidRequirement as exc:
            raise RuntimeError(f"{source} contains an invalid requirement") from exc
        name = _normalize_package_name(requirement.name)
        if name not in packages:
            continue
        specifiers = list(requirement.specifier)
        if (
            len(specifiers) != 1
            or specifiers[0].operator != "=="
            or "*" in specifiers[0].version
            or requirement.marker is not None
        ):
            raise RuntimeError(f"{source} must exactly pin {name} with ==")
        baseline[name] = specifiers[0].version

    missing = packages - baseline.keys()
    if missing:
        missing_names = ", ".join(sorted(missing))
        raise RuntimeError(f"{source} must exactly pin packages: {missing_names}")
    return baseline


def _load_requirement_file_pins(path: Path, packages: frozenset[str], source: str) -> dict[str, str]:
    dependencies: list[object] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        dependency = raw_line.partition("#")[0].strip()
        if dependency:
            dependencies.append(dependency)
    return _load_exact_pins(dependencies, packages, source)


def load_agent_dependency_baseline(path: Path = PYPROJECT_PATH) -> dict[str, str]:
    """Read exact Agent versions from the canonical project dependency declaration."""

    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    dependencies = project["dependencies"]
    return _load_exact_pins(dependencies, AGENT_RUNTIME_PACKAGES, "pyproject.toml dependencies")


def load_agent_requirements_baseline(path: Path = REQUIREMENTS_PATH) -> dict[str, str]:
    """Read exact Agent versions from the production lock input requirements."""

    return _load_requirement_file_pins(path, AGENT_RUNTIME_PACKAGES, "requirements.txt")


def load_development_dependency_baseline(path: Path = PYPROJECT_PATH) -> dict[str, str]:
    """Read exact development tool versions from the project dev extra."""

    project = tomllib.loads(path.read_text(encoding="utf-8"))["project"]
    optional_dependencies = project["optional-dependencies"]
    dependencies = optional_dependencies["dev"]
    return _load_exact_pins(dependencies, DEVELOPMENT_PACKAGES, "pyproject.toml dev dependencies")


def load_development_requirements_baseline(path: Path = DEV_REQUIREMENTS_PATH) -> dict[str, str]:
    """Read exact development tool versions from the hashed lock input."""

    return _load_requirement_file_pins(path, DEVELOPMENT_PACKAGES, "requirements-dev.txt")


def _installed_version_mismatches(baseline: dict[str, str]) -> list[str]:
    mismatches: list[str] = []
    for package, expected in sorted(baseline.items()):
        try:
            actual = version(package)
        except PackageNotFoundError:
            mismatches.append(f"{package}: missing (expected {expected})")
            continue
        if actual != expected:
            mismatches.append(f"{package}: {actual} (expected {expected})")
    return mismatches


def verify_agent_dependency_baseline() -> None:
    baseline = load_agent_dependency_baseline()
    requirements_baseline = load_agent_requirements_baseline()
    mismatches = _installed_version_mismatches(baseline)
    if requirements_baseline != baseline:
        mismatches.append("requirements.txt Agent pins do not match pyproject.toml")

    try:
        from langchain.agents import create_agent
    except ImportError as exc:
        mismatches.append(f"langchain.agents.create_agent: unavailable ({exc})")
    else:
        if not callable(create_agent):
            mismatches.append("langchain.agents.create_agent: not callable")

    if mismatches:
        details = "\n".join(f"- {item}" for item in mismatches)
        raise RuntimeError(f"CRM Agent dependency baseline mismatch:\n{details}")


def verify_development_dependency_baseline() -> None:
    baseline = load_development_dependency_baseline()
    requirements_baseline = load_development_requirements_baseline()
    mismatches = _installed_version_mismatches(baseline)
    if requirements_baseline != baseline:
        mismatches.append("requirements-dev.txt pins do not match pyproject.toml dev dependencies")
    if mismatches:
        details = "\n".join(f"- {item}" for item in mismatches)
        raise RuntimeError(f"CRM development dependency baseline mismatch:\n{details}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--include-dev",
        action="store_true",
        help="Also verify the exact development and CI tool baseline",
    )
    args = parser.parse_args()

    verify_agent_dependency_baseline()
    print("CRM Agent dependency baseline verified.")
    if args.include_dev:
        verify_development_dependency_baseline()
        print("CRM development dependency baseline verified.")


if __name__ == "__main__":
    main()
