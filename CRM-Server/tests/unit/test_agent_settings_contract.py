"""Public configuration contracts after retiring unused Agent 1.0 settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from app.core.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


RETIRED_AGENT_SETTINGS = (
    "MULTI_TOOL_ENABLED",
    "REACT_ENABLED",
    "AGENT_ENABLED",
    "WORKFLOW_ENABLED",
    "REACT_MAX_ROUNDS",
    "REACT_SINGLE_ROUND_TIMEOUT",
    "REACT_TOTAL_TIMEOUT",
    "AGENT_SESSION_TIMEOUT",
    "WORKFLOW_SESSION_TIMEOUT",
    "AGENT_THREAD_POOL_SIZE",
    "AGENT_MAX_CONCURRENT",
    "AGENT_USER_RATE_LIMIT",
    "AGENT_GLOBAL_RATE_LIMIT",
)

CURRENT_AGENT_DEFAULTS = {
    "AGENT_TIMEOUT": 180,
    "AGENT_ROOT_DECISION_TIMEOUT": 90.0,
    "AGENT_QUERY_SEMANTIC_TIMEOUT": 90.0,
    "AGENT_STRUCTURED_STREAM_CHUNK_TIMEOUT": 75.0,
    "AGENT_STRUCTURED_MAX_TOKENS": 1024,
    "AGENT_INTERNAL_API_BASE_URL": "http://127.0.0.1:8000/api",
    "AGENT_TURN_EXECUTION_LEASE_SECONDS": 30,
    "AGENT_TURN_EXECUTION_MAX_ATTEMPTS": 3,
    "AGENT_TURN_RECOVERY_ENABLED": True,
    "AGENT_TURN_RECOVERY_INTERVAL_SECONDS": 10,
    "AGENT_TURN_RECOVERY_BATCH_SIZE": 20,
    "AGENT_WORKER_TOKEN_SECONDS": 120,
}


@pytest.fixture(autouse=True)
def isolated_agent_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (*RETIRED_AGENT_SETTINGS, *CURRENT_AGENT_DEFAULTS):
        monkeypatch.delenv(name, raising=False)


def test_retired_settings_are_not_exposed_by_the_public_settings_contract() -> None:
    settings = Settings(_env_file=None)

    assert set(RETIRED_AGENT_SETTINGS).isdisjoint(settings.model_dump())
    assert all(not hasattr(settings, name) for name in RETIRED_AGENT_SETTINGS)


@pytest.mark.parametrize("name", RETIRED_AGENT_SETTINGS)
def test_retired_constructor_keys_are_ignored_even_with_invalid_old_values(name: str) -> None:
    settings = Settings(_env_file=None, **{name: "not-a-valid-legacy-value"})

    assert name not in settings.model_dump()


def test_current_agent_defaults_are_preserved() -> None:
    values = Settings(_env_file=None).model_dump()

    assert {name: values[name] for name in CURRENT_AGENT_DEFAULTS} == CURRENT_AGENT_DEFAULTS


def test_dotenv_ignores_retired_keys_and_loads_all_current_agent_settings(tmp_path: Path) -> None:
    expected = {
        "AGENT_TIMEOUT": 240,
        "AGENT_ROOT_DECISION_TIMEOUT": 91.5,
        "AGENT_QUERY_SEMANTIC_TIMEOUT": 92.5,
        "AGENT_STRUCTURED_STREAM_CHUNK_TIMEOUT": 76.5,
        "AGENT_STRUCTURED_MAX_TOKENS": 2048,
        "AGENT_INTERNAL_API_BASE_URL": "http://127.0.0.1:9000/api",
        "AGENT_TURN_EXECUTION_LEASE_SECONDS": 45,
        "AGENT_TURN_EXECUTION_MAX_ATTEMPTS": 5,
        "AGENT_TURN_RECOVERY_ENABLED": False,
        "AGENT_TURN_RECOVERY_INTERVAL_SECONDS": 15,
        "AGENT_TURN_RECOVERY_BATCH_SIZE": 25,
        "AGENT_WORKER_TOKEN_SECONDS": 180,
    }
    lines = [f"{name}=not-a-valid-legacy-value" for name in RETIRED_AGENT_SETTINGS]
    lines.extend(f"{name}={value}" for name, value in expected.items())
    env_file = tmp_path / ".env"
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    values = Settings(_env_file=env_file).model_dump()

    assert set(RETIRED_AGENT_SETTINGS).isdisjoint(values)
    assert {name: values[name] for name in expected} == expected


def test_process_environment_ignores_retired_keys_and_keeps_current_precedence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    for name in RETIRED_AGENT_SETTINGS:
        monkeypatch.setenv(name, "not-a-valid-legacy-value")
    monkeypatch.setenv("AGENT_TIMEOUT", "240")
    env_file = tmp_path / ".env"
    env_file.write_text("AGENT_TIMEOUT=200\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.AGENT_TIMEOUT == 240
    assert set(RETIRED_AGENT_SETTINGS).isdisjoint(settings.model_dump())


@pytest.mark.parametrize(
    "name",
    ["AGENT_ROOT_DECISION_TIMEOUT", "AGENT_STRUCTURED_MAX_TOKENS", "AGENT_TURN_RECOVERY_ENABLED"],
)
def test_current_agent_settings_still_reject_invalid_environment_values(
    name: str, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(name, "not-a-valid-current-value")

    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)

    assert any(item["loc"] == (name,) for item in error.value.errors())
