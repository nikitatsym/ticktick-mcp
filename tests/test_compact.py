"""Tests for grouped tool dispatch (post-v2.5).

Differences from v1 tests:
- `_dispatch` returns native Python objects (dicts/lists/strings/None), NOT
  JSON strings. The earlier `json.loads(_dispatch(...))` was a bug (it
  always raised after commit 6cefd85 removed double-serialization).
- Wrong-group and unknown-operation now raise `ValueError` instead of
  returning `{"error": "..."}`.
- `_parse_bool` was removed — bool coercion happens in `_build_params_model`
  via a Pydantic `field_validator`. Covered in `test_pydantic_bool_coercion`
  below.
"""

import inspect
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from ticktick_mcp import tools as _tools_module
from ticktick_mcp.registry import Group
from ticktick_mcp.tools import ticktick_read, ticktick_write, ticktick_delete
from ticktick_mcp.server import _build_help, _dispatch, _group_ops, _to_pascal


# ── Registry validation ─────────────────────────────────────────────────────


def _count_by_group(group: Group) -> int:
    return sum(
        1 for _, fn in inspect.getmembers(_tools_module, inspect.isfunction)
        if getattr(fn, "_mcp_group", None) is group
    )


def test_read_count() -> None:
    assert _count_by_group(ticktick_read) == 7


def test_write_count() -> None:
    assert _count_by_group(ticktick_write) == 5


def test_delete_count() -> None:
    assert _count_by_group(ticktick_delete) == 2


def test_total_operations() -> None:
    total = sum(
        1 for _, fn in inspect.getmembers(_tools_module, inspect.isfunction)
        if hasattr(fn, "_mcp_group")
    )
    assert total == 15


# ── _to_pascal ───────────────────────────────────────────────────────────────


def test_to_pascal() -> None:
    assert _to_pascal("get_today") == "GetToday"
    assert _to_pascal("create_task") == "CreateTask"
    assert _to_pascal("get_project_with_data") == "GetProjectWithData"
    assert _to_pascal("list_projects") == "ListProjects"


# ── Help text ────────────────────────────────────────────────────────────────


def test_help_read() -> None:
    text = _build_help("ticktick_read")
    assert "7 operations available." in text
    for op in ("GetToday", "GetInbox", "GetInboxId", "ListProjects",
               "GetProject", "GetProjectWithData", "GetTask"):
        assert op in text
    assert "CreateTask" not in text
    assert "DeleteTask" not in text


def test_help_write() -> None:
    text = _build_help("ticktick_write")
    assert "5 operations available." in text
    for op in ("CreateTask", "UpdateTask", "CompleteTask", "CreateProject", "UpdateProject"):
        assert op in text


def test_help_delete() -> None:
    text = _build_help("ticktick_delete")
    assert "2 operations available." in text
    for op in ("DeleteTask", "DeleteProject"):
        assert op in text


def test_help_includes_params() -> None:
    text = _build_help("ticktick_read")
    assert "projectId" in text


def test_help_surfaces_docstring_body() -> None:
    """Non-type constraints in docstring body must appear in help output."""
    text = _build_help("ticktick_write")
    assert "<brief>" in text
    assert "YYYY-MM-DD" in text or "MCP_TICKTICK_TIMEZONE" in text


# ── Scope mismatch ───────────────────────────────────────────────────────────


def test_read_op_via_write_tool() -> None:
    with pytest.raises(ValueError, match="ticktick_read"):
        _dispatch("GetToday", "ticktick_write", {})


def test_write_op_via_read_tool() -> None:
    with pytest.raises(ValueError, match="ticktick_write"):
        _dispatch("CreateTask", "ticktick_read", {})


def test_delete_op_via_write_tool() -> None:
    with pytest.raises(ValueError, match="ticktick_delete"):
        _dispatch("DeleteTask", "ticktick_write", {})


# ── Unknown operation ────────────────────────────────────────────────────────


def test_unknown_operation() -> None:
    with pytest.raises(ValueError, match="Unknown operation"):
        _dispatch("NonExistent", "ticktick_read", {})


# ── Pydantic bool coercion ───────────────────────────────────────────────────


def test_pydantic_bool_coercion_string_true() -> None:
    model = getattr(_tools_module.create_task, "_params_model")
    v = model.model_validate({"title": "T", "brief": "B", "isAllDay": "true"})
    assert v.isAllDay is True


def test_pydantic_bool_coercion_string_false() -> None:
    model = getattr(_tools_module.create_task, "_params_model")
    v = model.model_validate({"title": "T", "brief": "B", "isAllDay": "false"})
    assert v.isAllDay is False


def test_pydantic_bool_coercion_yes_no() -> None:
    model = getattr(_tools_module.create_task, "_params_model")
    v = model.model_validate({"title": "T", "brief": "B", "isAllDay": "yes"})
    assert v.isAllDay is True
    v2 = model.model_validate({"title": "T", "brief": "B", "isAllDay": "no"})
    assert v2.isAllDay is False


# ── Read dispatch (mocked client) ───────────────────────────────────────────


@pytest.fixture()
def mock_client() -> Iterator[MagicMock]:
    client = MagicMock()
    with patch("ticktick_mcp.tools._get_client", return_value=client):
        yield client


def test_get_today(mock_client: MagicMock) -> None:
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "Task 1", "status": 0, "content": "<brief>Do stuff</brief>"}
    ]
    result = _dispatch("GetToday", "ticktick_read", {})
    assert isinstance(result, list)
    assert result[0]["id"] == "1"
    mock_client.get_today_tasks.assert_called_once()


def test_get_today_slim_strips_content(mock_client: MagicMock) -> None:
    """GetToday always returns slim form — no content field."""
    mock_client.get_today_tasks.return_value = [
        {"id": "1", "title": "T", "status": 0,
         "content": "<brief>B</brief>", "sortOrder": 123}
    ]
    result = _dispatch("GetToday", "ticktick_read", {})
    assert "sortOrder" not in result[0]
    assert "content" not in result[0]


def test_get_inbox(mock_client: MagicMock) -> None:
    mock_client.get_inbox_with_data.return_value = {
        "project": {"id": "inbox1"},
        "tasks": [{"id": "t1", "title": "Inbox task", "status": 0}],
    }
    result = _dispatch("GetInbox", "ticktick_read", {})
    assert "tasks" in result
    mock_client.get_inbox_with_data.assert_called_once()


def test_get_inbox_id(mock_client: MagicMock) -> None:
    mock_client.get_inbox_id.return_value = "inbox123"
    result = _dispatch("GetInboxId", "ticktick_read", {})
    assert result["inboxId"] == "inbox123"


def test_list_projects(mock_client: MagicMock) -> None:
    mock_client.list_projects.return_value = [{"id": "p1", "name": "Work"}]
    result = _dispatch("ListProjects", "ticktick_read", {})
    assert len(result) == 1
    assert result[0]["name"] == "Work"


def test_get_project(mock_client: MagicMock) -> None:
    mock_client.get_project.return_value = {"id": "p1", "name": "Work"}
    result = _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})
    assert result["id"] == "p1"
    mock_client.get_project.assert_called_with("p1")


def test_get_project_with_data(mock_client: MagicMock) -> None:
    mock_client.get_project_with_data.return_value = {
        "project": {"id": "p1"},
        "tasks": [{"id": "t1", "title": "T", "status": 0}],
    }
    result = _dispatch("GetProjectWithData", "ticktick_read", {"projectId": "p1"})
    assert "tasks" in result
    mock_client.get_project_with_data.assert_called_with("p1")


def test_get_task(mock_client: MagicMock) -> None:
    mock_client.get_task.return_value = {
        "id": "t1", "title": "Buy milk", "projectId": "p1",
    }
    result = _dispatch("GetTask", "ticktick_read",
                       {"projectId": "p1", "taskId": "t1"})
    assert result["title"] == "Buy milk"
    mock_client.get_task.assert_called_with("p1", "t1")


# ── Write dispatch ───────────────────────────────────────────────────────────


def test_create_task(mock_client: MagicMock) -> None:
    mock_client.create_task.return_value = {
        "id": "new1", "title": "Buy milk",
        "content": "<brief>Buy milk</brief>",
    }
    result = _dispatch("CreateTask", "ticktick_write", {
        "title": "Buy milk", "brief": "Buy milk",
    })
    assert result["id"] == "new1"
    sent = mock_client.create_task.call_args[0][0]
    assert "<brief>Buy milk</brief>" in sent["content"]


def test_create_task_no_brief_no_content_validates(mock_client: MagicMock) -> None:
    """Without brief param AND without content tag, _validate_brief raises."""
    with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
        _dispatch("CreateTask", "ticktick_write",
                  {"title": "T", "content": "no tag"})


def test_update_task(mock_client: MagicMock) -> None:
    mock_client.update_task.return_value = {
        "id": "t1", "title": "Updated", "projectId": "p1",
    }
    result = _dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1", "title": "Updated",
    })
    assert result["title"] == "Updated"
    mock_client.update_task.assert_called_once()


def test_complete_task(mock_client: MagicMock) -> None:
    result = _dispatch("CompleteTask", "ticktick_write",
                       {"projectId": "p1", "taskId": "t1"})
    assert "completed" in result
    mock_client.complete_task.assert_called_with("p1", "t1")


def test_create_project(mock_client: MagicMock) -> None:
    mock_client.create_project.return_value = {
        "id": "p1", "name": "New", "viewMode": "kanban",
    }
    result = _dispatch("CreateProject", "ticktick_write",
                       {"name": "New", "viewMode": "kanban"})
    assert result["name"] == "New"
    sent = mock_client.create_project.call_args[0][0]
    assert sent["viewMode"] == "kanban"


def test_update_project(mock_client: MagicMock) -> None:
    mock_client.update_project.return_value = {"id": "p1", "name": "Renamed"}
    result = _dispatch("UpdateProject", "ticktick_write", {
        "projectId": "p1", "name": "Renamed",
    })
    assert result["name"] == "Renamed"
    mock_client.update_project.assert_called_with("p1", {"name": "Renamed"})


# ── Delete dispatch ──────────────────────────────────────────────────────────


def test_delete_task(mock_client: MagicMock) -> None:
    result = _dispatch("DeleteTask", "ticktick_delete",
                       {"projectId": "p1", "taskId": "t1"})
    assert "deleted" in result
    mock_client.delete_task.assert_called_with("p1", "t1")


def test_delete_project(mock_client: MagicMock) -> None:
    result = _dispatch("DeleteProject", "ticktick_delete", {"projectId": "p1"})
    assert "deleted" in result
    mock_client.delete_project.assert_called_with("p1")


# ── Params edge cases ────────────────────────────────────────────────────────


def test_empty_params(mock_client: MagicMock) -> None:
    mock_client.list_projects.return_value = []
    result = _dispatch("ListProjects", "ticktick_read", {})
    assert result == []
