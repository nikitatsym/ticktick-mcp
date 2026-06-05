"""Pydantic validation: unknown keys, missing required, wrong types.

All raise `ValueError` with field-level detail, pointing the agent at
`operation='schema'` for the full spec.
"""

import pytest

from ticktick_mcp.server import _dispatch


def test_unknown_param_raises():
    with pytest.raises(ValueError, match="Invalid params for CreateTask"):
        _dispatch("CreateTask", "ticktick_write", {"title": "T", "bogus": 42})


def test_unknown_param_names_offending_field():
    with pytest.raises(ValueError, match="bogus"):
        _dispatch("CreateTask", "ticktick_write", {"title": "T", "bogus": 42})


def test_validation_error_points_at_schema():
    with pytest.raises(ValueError, match="operation='schema'"):
        _dispatch("CreateTask", "ticktick_write", {"title": "T", "bogus": 42})


def test_missing_required_raises():
    with pytest.raises(ValueError, match="Invalid params for CreateTask"):
        _dispatch("CreateTask", "ticktick_write", {})


def test_wrong_type_raises():
    with pytest.raises(ValueError, match="Invalid params for CreateProject"):
        _dispatch("CreateProject", "ticktick_write", {"name": "X", "viewMode": 42})


def test_unknown_operation_raises():
    with pytest.raises(ValueError, match="Unknown operation"):
        _dispatch("Bogus", "ticktick_read", {})


def test_op_in_wrong_group_raises_with_hint():
    with pytest.raises(ValueError, match="belongs to 'ticktick_read'"):
        _dispatch("GetToday", "ticktick_write", {})


def test_delete_op_in_write_group_raises():
    with pytest.raises(ValueError, match="belongs to 'ticktick_delete'"):
        _dispatch("DeleteTask", "ticktick_write", {})
