"""Database exception responses must distinguish schema drift from transient errors."""

import json

import pytest
from fastapi import Request
from sqlalchemy.exc import OperationalError

from app.core.exceptions import (
    DATABASE_SCHEMA_MISMATCH_DETAIL,
    is_database_schema_mismatch,
    sqlalchemy_exception_handler,
)


def _request(path: str = "/api/v1/assistant/conversation") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )


def _database_error(code: int, message: str) -> OperationalError:
    return OperationalError("SELECT hidden_sql", {}, RuntimeError(code, message))


@pytest.mark.parametrize("code", [1054, 1146])
async def test_schema_errors_return_a_migration_specific_response(code):
    exc = _database_error(code, "schema changed")
    response = await sqlalchemy_exception_handler(_request(), exc)
    body = json.loads(response.body)

    assert response.status_code == 500
    assert body["error_code"] == "DATABASE_SCHEMA_MISMATCH"
    assert body["detail"] == DATABASE_SCHEMA_MISMATCH_DETAIL
    assert "hidden_sql" not in response.body.decode()


async def test_other_database_errors_keep_the_generic_response():
    response = await sqlalchemy_exception_handler(_request(), _database_error(2003, "connection refused"))
    body = json.loads(response.body)

    assert response.status_code == 500
    assert body["error_code"] == "DATABASE_ERROR"
    assert body["detail"] == "数据库操作失败"


@pytest.mark.parametrize("code,expected", [(1054, True), (1146, True), (2003, False)])
def test_schema_mismatch_detection_reads_nested_mysql_errors(code, expected):
    assert is_database_schema_mismatch(_database_error(code, "database error")) is expected
