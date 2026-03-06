"""Tests for compact mode (3 meta-tools)."""

import json
from unittest.mock import MagicMock, patch

import pytest

from ticktick_mcp.server_compact import (
    _OPERATIONS,
    _SCOPE_NAMES,
    _build_help,
    _dispatch,
    _parse_bool,
)


# ── Registry validation ─────────────────────────────────────────────────────


def test_all_scopes_valid():
    for op, (scope, _, _) in _OPERATIONS.items():
        assert scope in _SCOPE_NAMES, f"{op} has unknown scope {scope!r}"


def test_read_count():
    count = sum(1 for _, (s, _, _) in _OPERATIONS.items() if s == "read")
    assert count == 7


def test_write_count():
    count = sum(1 for _, (s, _, _) in _OPERATIONS.items() if s == "write")
    assert count == 6


def test_delete_count():
    count = sum(1 for _, (s, _, _) in _OPERATIONS.items() if s == "delete")
    assert count == 2


def test_total_operations():
    assert len(_OPERATIONS) == 15


# ── Help text ────────────────────────────────────────────────────────────────


def test_help_read():
    text = _build_help("read")
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
    text = _build_help("write")
    assert "6 operations available:" in text
    assert "CreateTask" in text
    assert "UpdateTask" in text
    assert "CompleteTask" in text
    assert "CreateProject" in text
    assert "UpdateProject" in text
    assert "BatchCreateTasks" in text


def test_help_delete():
    text = _build_help("delete")
    assert "2 operations available:" in text
    assert "DeleteTask" in text
    assert "DeleteProject" in text


# ── Scope mismatch ───────────────────────────────────────────────────────────


def test_read_op_via_write_tool():
    result = json.loads(_dispatch("GetToday", "write", "{}"))
    assert "error" in result
    assert "read operation" in result["error"]
    assert "ticktick_read" in result["error"]


def test_write_op_via_read_tool():
    result = json.loads(_dispatch("CreateTask", "read", "{}"))
    assert "error" in result
    assert "write operation" in result["error"]
    assert "ticktick_write" in result["error"]


def test_delete_op_via_write_tool():
    result = json.loads(_dispatch("DeleteTask", "write", "{}"))
    assert "error" in result
    assert "delete operation" in result["error"]
    assert "ticktick_delete" in result["error"]


# ── Unknown operation ────────────────────────────────────────────────────────


def test_unknown_operation():
    result = json.loads(_dispatch("NonExistent", "read", "{}"))
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
    with patch("ticktick_mcp.server_compact._get_client", return_value=client):
        yield client


def test_get_today(mock_client):
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "Task 1", "status": 0, "content": "<brief>Do stuff</brief>"}
    ]
    result = json.loads(_dispatch("GetToday", "read", "{}"))
    assert isinstance(result, list)
    assert result[0]["id"] == "1"
    mock_client.get_today_tasks.assert_called_once()


def test_get_today_slim(mock_client):
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "T", "status": 0, "content": "<brief>B</brief>", "sortOrder": 123}
    ]
    result = json.loads(_dispatch("GetToday", "read", '{"slim": true}'))
    assert "sortOrder" not in result[0]


def test_get_inbox(mock_client):
    mock_client.get_inbox_with_data.return_value = {
        "project": {"id": "inbox1"},
        "tasks": [{"id": "t1", "title": "Inbox task", "status": 0}],
    }
    result = json.loads(_dispatch("GetInbox", "read", "{}"))
    assert "tasks" in result
    mock_client.get_inbox_with_data.assert_called_once()


def test_get_inbox_id(mock_client):
    mock_client.get_inbox_id.return_value = "inbox123"
    result = json.loads(_dispatch("GetInboxId", "read", "{}"))
    assert result["inboxId"] == "inbox123"


def test_list_projects(mock_client):
    mock_client.list_projects.return_value = [{"id": "p1", "name": "Work"}]
    result = json.loads(_dispatch("ListProjects", "read", "{}"))
    assert len(result) == 1
    assert result[0]["name"] == "Work"


def test_get_project(mock_client):
    mock_client.get_project.return_value = {"id": "p1", "name": "Work"}
    result = json.loads(_dispatch("GetProject", "read", '{"projectId": "p1"}'))
    assert result["id"] == "p1"
    mock_client.get_project.assert_called_with("p1")


def test_get_project_with_data(mock_client):
    mock_client.get_project_with_data.return_value = {
        "project": {"id": "p1"},
        "tasks": [{"id": "t1", "title": "T", "status": 0}],
    }
    result = json.loads(_dispatch("GetProjectWithData", "read", '{"projectId": "p1"}'))
    assert "tasks" in result
    mock_client.get_project_with_data.assert_called_with("p1")


def test_get_task(mock_client):
    mock_client.get_task.return_value = {"id": "t1", "title": "Buy milk", "projectId": "p1"}
    result = json.loads(_dispatch("GetTask", "read", '{"projectId": "p1", "taskId": "t1"}'))
    assert result["title"] == "Buy milk"
    mock_client.get_task.assert_called_with("p1", "t1")


# ── Write dispatch ───────────────────────────────────────────────────────────


def test_create_task(mock_client):
    mock_client.create_task.return_value = {"id": "new1", "title": "Buy milk"}
    result = json.loads(_dispatch("CreateTask", "write", json.dumps({
        "title": "Buy milk",
        "brief": "Buy milk",
    })))
    assert result["id"] == "new1"
    call_args = mock_client.create_task.call_args[0][0]
    assert "<brief>Buy milk</brief>" in call_args["content"]


def test_create_task_no_brief_validates(mock_client):
    """Without brief param, content must have brief tag (when REQUIRE_BRIEF is on)."""
    with patch("ticktick_mcp.server_compact._validate_brief", side_effect=ValueError("must contain")):
        with pytest.raises(ValueError, match="must contain"):
            _dispatch("CreateTask", "write", json.dumps({"title": "T", "content": "no tag"}))


def test_update_task(mock_client):
    mock_client.update_task.return_value = {"id": "t1", "title": "Updated"}
    result = json.loads(_dispatch("UpdateTask", "write", json.dumps({
        "taskId": "t1", "projectId": "p1", "title": "Updated",
    })))
    assert result["title"] == "Updated"
    mock_client.update_task.assert_called_once()


def test_update_task_with_brief_fetches_existing(mock_client):
    mock_client.get_task.return_value = {"id": "t1", "content": "old stuff"}
    mock_client.update_task.return_value = {"id": "t1", "content": "<brief>New</brief>\nold stuff"}
    result = json.loads(_dispatch("UpdateTask", "write", json.dumps({
        "taskId": "t1", "projectId": "p1", "brief": "New",
    })))
    mock_client.get_task.assert_called_with("p1", "t1")
    call_args = mock_client.update_task.call_args[0][1]
    assert "<brief>New</brief>" in call_args["content"]


def test_complete_task(mock_client):
    result = _dispatch("CompleteTask", "write", json.dumps({"projectId": "p1", "taskId": "t1"}))
    assert "completed" in result
    mock_client.complete_task.assert_called_with("p1", "t1")


def test_create_project(mock_client):
    mock_client.create_project.return_value = {"id": "p1", "name": "New"}
    result = json.loads(_dispatch("CreateProject", "write", json.dumps({"name": "New", "viewMode": "kanban"})))
    assert result["name"] == "New"
    call_args = mock_client.create_project.call_args[0][0]
    assert call_args["viewMode"] == "kanban"


def test_update_project(mock_client):
    mock_client.update_project.return_value = {"id": "p1", "name": "Renamed"}
    result = json.loads(_dispatch("UpdateProject", "write", json.dumps({
        "projectId": "p1", "name": "Renamed",
    })))
    assert result["name"] == "Renamed"
    mock_client.update_project.assert_called_with("p1", {"name": "Renamed"})


def test_batch_create_tasks(mock_client):
    mock_client.batch_create_tasks.return_value = [{"id": "t1"}, {"id": "t2"}]
    tasks = [
        {"title": "A", "brief": "Task A"},
        {"title": "B", "brief": "Task B"},
    ]
    result = json.loads(_dispatch("BatchCreateTasks", "write", json.dumps({"tasks": tasks})))
    assert len(result) == 2
    call_args = mock_client.batch_create_tasks.call_args[0][0]
    assert "<brief>Task A</brief>" in call_args[0]["content"]


# ── Delete dispatch ──────────────────────────────────────────────────────────


def test_delete_task(mock_client):
    result = _dispatch("DeleteTask", "delete", json.dumps({"projectId": "p1", "taskId": "t1"}))
    assert "deleted" in result
    mock_client.delete_task.assert_called_with("p1", "t1")


def test_delete_project(mock_client):
    result = _dispatch("DeleteProject", "delete", json.dumps({"projectId": "p1"}))
    assert "deleted" in result
    mock_client.delete_project.assert_called_with("p1")


# ── Params edge cases ────────────────────────────────────────────────────────


def test_empty_params(mock_client):
    mock_client.list_projects.return_value = []
    result = json.loads(_dispatch("ListProjects", "read", ""))
    assert result == []


def test_whitespace_params(mock_client):
    mock_client.list_projects.return_value = []
    result = json.loads(_dispatch("ListProjects", "read", "   "))
    assert result == []


def test_none_like_params(mock_client):
    mock_client.list_projects.return_value = []
    result = json.loads(_dispatch("ListProjects", "read", "{}"))
    assert result == []
