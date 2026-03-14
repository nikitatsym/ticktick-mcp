"""Tests for grouped tool dispatch."""

import inspect
import json
from unittest.mock import MagicMock, patch

import pytest

from ticktick_mcp import tools as _tools_module
from ticktick_mcp.tools import ticktick_read, ticktick_write, ticktick_delete
from ticktick_mcp.server import (
    _build_help,
    _dispatch,
    _group_ops,
    _parse_bool,
    _to_pascal,
)


# ── Registry validation ─────────────────────────────────────────────────────


def _count_by_group(group) -> int:
    return sum(
        1 for _, fn in inspect.getmembers(_tools_module, inspect.isfunction)
        if getattr(fn, "_mcp_group", None) is group
    )


def test_read_count():
    assert _count_by_group(ticktick_read) == 7


def test_write_count():
    assert _count_by_group(ticktick_write) == 5


def test_delete_count():
    assert _count_by_group(ticktick_delete) == 2


def test_total_operations():
    total = sum(
        1 for _, fn in inspect.getmembers(_tools_module, inspect.isfunction)
        if hasattr(fn, "_mcp_group")
    )
    assert total == 15


# ── _to_pascal ───────────────────────────────────────────────────────────────


def test_to_pascal():
    assert _to_pascal("get_today") == "GetToday"
    assert _to_pascal("create_task") == "CreateTask"
    assert _to_pascal("get_project_with_data") == "GetProjectWithData"
    assert _to_pascal("list_projects") == "ListProjects"


# ── Help text ────────────────────────────────────────────────────────────────


def test_help_read():
    text = _build_help("ticktick_read")
    assert "7 operations available:" in text
    assert "GetToday" in text
    assert "GetInbox" in text
    assert "GetInboxId" in text
    assert "ListProjects" in text
    assert "GetProject" in text
    assert "GetProjectWithData" in text
    assert "GetTask" in text
    # Should NOT include write/delete ops
    assert "CreateTask" not in text
    assert "DeleteTask" not in text


def test_help_write():
    text = _build_help("ticktick_write")
    assert "5 operations available:" in text
    assert "CreateTask" in text
    assert "UpdateTask" in text
    assert "CompleteTask" in text
    assert "CreateProject" in text
    assert "UpdateProject" in text


def test_help_delete():
    text = _build_help("ticktick_delete")
    assert "2 operations available:" in text
    assert "DeleteTask" in text
    assert "DeleteProject" in text


def test_help_includes_params():
    """Help text should auto-include function parameter names."""
    text = _build_help("ticktick_read")
    assert "projectId" in text


# ── Scope mismatch ───────────────────────────────────────────────────────────


def test_read_op_via_write_tool():
    result = json.loads(_dispatch("GetToday", "ticktick_write", {}))
    assert "error" in result
    assert "ticktick_read" in result["error"]


def test_write_op_via_read_tool():
    result = json.loads(_dispatch("CreateTask", "ticktick_read", {}))
    assert "error" in result
    assert "ticktick_write" in result["error"]


def test_delete_op_via_write_tool():
    result = json.loads(_dispatch("DeleteTask", "ticktick_write", {}))
    assert "error" in result
    assert "ticktick_delete" in result["error"]


# ── Unknown operation ────────────────────────────────────────────────────────


def test_unknown_operation():
    result = json.loads(_dispatch("NonExistent", "ticktick_read", {}))
    assert "error" in result
    assert "Unknown operation" in result["error"]
    assert "help" in result["error"]


# ── _parse_bool ──────────────────────────────────────────────────────────────


def test_parse_bool_none_uses_default():
    assert _parse_bool(None, True) is True
    assert _parse_bool(None, False) is False


def test_parse_bool_bool():
    assert _parse_bool(True, False) is True
    assert _parse_bool(False, True) is False


def test_parse_bool_string():
    assert _parse_bool("true", False) is True
    assert _parse_bool("1", False) is True
    assert _parse_bool("yes", False) is True
    assert _parse_bool("false", True) is False
    assert _parse_bool("no", True) is False


# ── Read dispatch (mocked client) ───────────────────────────────────────────


@pytest.fixture()
def mock_client():
    client = MagicMock()
    with patch("ticktick_mcp.tools._get_client", return_value=client):
        yield client


def test_get_today(mock_client):
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "Task 1", "status": 0, "content": "<brief>Do stuff</brief>"}
    ]
    result = json.loads(_dispatch("GetToday", "ticktick_read", {}))
    assert isinstance(result, list)
    assert result[0]["id"] == "1"
    mock_client.get_today_tasks.assert_called_once()


def test_get_today_slim(mock_client):
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "T", "status": 0, "content": "<brief>B</brief>", "sortOrder": 123}
    ]
    result = json.loads(_dispatch("GetToday", "ticktick_read", {"slim": True}))
    assert "sortOrder" not in result[0]


def test_get_inbox(mock_client):
    mock_client.get_inbox_with_data.return_value = {
        "project": {"id": "inbox1"},
        "tasks": [{"id": "t1", "title": "Inbox task", "status": 0}],
    }
    result = json.loads(_dispatch("GetInbox", "ticktick_read", {}))
    assert "tasks" in result
    mock_client.get_inbox_with_data.assert_called_once()


def test_get_inbox_id(mock_client):
    mock_client.get_inbox_id.return_value = "inbox123"
    result = json.loads(_dispatch("GetInboxId", "ticktick_read", {}))
    assert result["inboxId"] == "inbox123"


def test_list_projects(mock_client):
    mock_client.list_projects.return_value = [{"id": "p1", "name": "Work"}]
    result = json.loads(_dispatch("ListProjects", "ticktick_read", {}))
    assert len(result) == 1
    assert result[0]["name"] == "Work"


def test_get_project(mock_client):
    mock_client.get_project.return_value = {"id": "p1", "name": "Work"}
    result = json.loads(_dispatch("GetProject", "ticktick_read", {"projectId": "p1"}))
    assert result["id"] == "p1"
    mock_client.get_project.assert_called_with("p1")


def test_get_project_with_data(mock_client):
    mock_client.get_project_with_data.return_value = {
        "project": {"id": "p1"},
        "tasks": [{"id": "t1", "title": "T", "status": 0}],
    }
    result = json.loads(_dispatch("GetProjectWithData", "ticktick_read", {"projectId": "p1"}))
    assert "tasks" in result
    mock_client.get_project_with_data.assert_called_with("p1")


def test_get_task(mock_client):
    mock_client.get_task.return_value = {"id": "t1", "title": "Buy milk", "projectId": "p1"}
    result = json.loads(_dispatch("GetTask", "ticktick_read", {"projectId": "p1", "taskId": "t1"}))
    assert result["title"] == "Buy milk"
    mock_client.get_task.assert_called_with("p1", "t1")


# ── Write dispatch ───────────────────────────────────────────────────────────


def test_create_task(mock_client):
    mock_client.create_task.return_value = {"id": "new1", "title": "Buy milk", "content": "<brief>Buy milk</brief>"}
    result = json.loads(_dispatch("CreateTask", "ticktick_write", {
        "title": "Buy milk",
        "brief": "Buy milk",
    }))
    assert result["id"] == "new1"
    call_args = mock_client.create_task.call_args[0][0]
    assert "<brief>Buy milk</brief>" in call_args["content"]


def test_create_task_no_brief_validates(mock_client):
    """Without brief param, content must have brief tag (when REQUIRE_BRIEF is on)."""
    with patch("ticktick_mcp.prepare._validate_brief", side_effect=ValueError("must contain")):
        with pytest.raises(ValueError, match="must contain"):
            _dispatch("CreateTask", "ticktick_write", {"title": "T", "content": "no tag"})


def test_update_task(mock_client):
    mock_client.update_task.return_value = {"id": "t1", "title": "Updated", "projectId": "p1"}
    result = json.loads(_dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1", "title": "Updated",
    }))
    assert result["title"] == "Updated"
    mock_client.update_task.assert_called_once()


def test_update_task_with_brief_fetches_existing(mock_client):
    mock_client.get_task.return_value = {"id": "t1", "content": "old stuff"}
    mock_client.update_task.return_value = {"id": "t1", "projectId": "p1", "content": "<brief>New</brief>\nold stuff"}
    result = json.loads(_dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1", "brief": "New",
    }))
    mock_client.get_task.assert_called_with("p1", "t1")
    call_args = mock_client.update_task.call_args[0][1]
    assert "<brief>New</brief>" in call_args["content"]


def test_complete_task(mock_client):
    result = _dispatch("CompleteTask", "ticktick_write", {"projectId": "p1", "taskId": "t1"})
    assert "completed" in result
    mock_client.complete_task.assert_called_with("p1", "t1")


def test_create_project(mock_client):
    mock_client.create_project.return_value = {"id": "p1", "name": "New", "viewMode": "kanban"}
    result = json.loads(_dispatch("CreateProject", "ticktick_write", {"name": "New", "viewMode": "kanban"}))
    assert result["name"] == "New"
    call_args = mock_client.create_project.call_args[0][0]
    assert call_args["viewMode"] == "kanban"


def test_update_project(mock_client):
    mock_client.update_project.return_value = {"id": "p1", "name": "Renamed"}
    result = json.loads(_dispatch("UpdateProject", "ticktick_write", {
        "projectId": "p1", "name": "Renamed",
    }))
    assert result["name"] == "Renamed"
    mock_client.update_project.assert_called_with("p1", {"name": "Renamed"})


# ── Delete dispatch ──────────────────────────────────────────────────────────


def test_delete_task(mock_client):
    result = _dispatch("DeleteTask", "ticktick_delete", {"projectId": "p1", "taskId": "t1"})
    assert "deleted" in result
    mock_client.delete_task.assert_called_with("p1", "t1")


def test_delete_project(mock_client):
    result = _dispatch("DeleteProject", "ticktick_delete", {"projectId": "p1"})
    assert "deleted" in result
    mock_client.delete_project.assert_called_with("p1")


# ── Params edge cases ────────────────────────────────────────────────────────


def test_empty_params(mock_client):
    mock_client.list_projects.return_value = []
    result = json.loads(_dispatch("ListProjects", "ticktick_read", {}))
    assert result == []
