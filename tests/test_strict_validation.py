"""Pydantic validation: unknown keys, missing required, wrong types.

All raise a ToolError from `_dispatch` with field-level detail, pointing the
agent at `operation='schema'` for the full spec.
"""

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from ticktick_mcp.server import _dispatch


def _error(operation: str, group: str, params: dict[str, object]) -> str:
    with pytest.raises(ToolError) as excinfo:
        _dispatch(operation, group, params)
    return str(excinfo.value)


def test_unknown_param_reports_error() -> None:
    assert "Invalid params for CreateTask" in _error(
        "CreateTask", "ticktick_write", {"title": "T", "bogus": 42}
    )


def test_unknown_param_names_offending_field() -> None:
    assert "bogus" in _error(
        "CreateTask", "ticktick_write", {"title": "T", "bogus": 42}
    )


def test_validation_error_points_at_schema() -> None:
    assert "operation='schema'" in _error(
        "CreateTask", "ticktick_write", {"title": "T", "bogus": 42}
    )


def test_missing_required_reports_error() -> None:
    assert "Invalid params for CreateTask" in _error(
        "CreateTask", "ticktick_write", {}
    )


def test_wrong_type_reports_error() -> None:
    assert "Invalid params for CreateProject" in _error(
        "CreateProject", "ticktick_write", {"name": "X", "viewMode": 42}
    )


def test_unknown_operation_reports_error() -> None:
    assert "Unknown operation" in _error("Bogus", "ticktick_read", {})


def test_op_in_wrong_group_reports_hint() -> None:
    assert "belongs to 'ticktick_read'" in _error(
        "GetToday", "ticktick_write", {}
    )


def test_delete_op_in_write_group_reports_hint() -> None:
    assert "belongs to 'ticktick_delete'" in _error(
        "DeleteTask", "ticktick_write", {}
    )
