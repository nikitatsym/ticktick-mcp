"""Compact mode: 3 meta-tools instead of 15 individual tools.

Enabled via TICKTICK_COMPACT=true. Follows the komodo-mcp pattern —
operation-based dispatch with ticktick_read / ticktick_write / ticktick_delete.
"""

import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .client import TickTickClient
from .server import (
    _DEFAULT_DESC,
    _DEFAULT_DESC_COMPACT,
    _DEFAULT_SLIM,
    _prepare_project,
    _prepare_task,
    _process_tasks,
    _slim_task,
    _verify_response,
)

mcp = FastMCP("ticktick")

_client: Optional[TickTickClient] = None


def _get_client() -> TickTickClient:
    global _client
    if _client is None:
        _client = TickTickClient(
            os.environ.get("TICKTICK_CLIENT_ID"),
            os.environ.get("TICKTICK_CLIENT_SECRET"),
        )
    return _client


# ── Operation registry ────────────────────────────────────────────────────────
# {name: (scope, param_names, docstring)}

_OPERATIONS: dict[str, tuple[str, list[str], str]] = {
    # read
    "GetToday": ("read", ["desc", "descCompact", "slim"], "Get all uncompleted tasks due today or earlier (overdue). Same as the 'Today' view in TickTick."),
    "GetInbox": ("read", ["desc", "descCompact", "slim"], "Get the Inbox project with all its tasks. The Inbox is NOT included in ListProjects."),
    "GetInboxId": ("read", [], "Get the Inbox project ID."),
    "ListProjects": ("read", [], "List all TickTick projects (task lists). Does NOT include the Inbox."),
    "GetProject": ("read", ["projectId"], "Get a TickTick project by ID."),
    "GetProjectWithData": ("read", ["projectId", "desc", "descCompact", "slim"], "Get a TickTick project with all its tasks and columns."),
    "GetTask": ("read", ["projectId", "taskId"], "Get a specific task by project ID and task ID."),
    # write
    "CreateTask": ("write", ["title", "projectId", "content", "desc", "brief", "startDate", "dueDate", "isAllDay", "priority", "tags", "timeZone", "reminders", "repeatFlag", "items"], "Create a new task. If projectId is omitted, goes to Inbox. Content must include <brief>summary</brief> tag. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0=none, 1=low, 3=medium, 5=high. reminders: iCal triggers e.g. [\"TRIGGER:-PT15M\"]. repeatFlag: iCal RRULE e.g. \"RRULE:FREQ=WEEKLY\"."),
    "UpdateTask": ("write", ["taskId", "projectId", "title", "content", "desc", "brief", "startDate", "dueDate", "isAllDay", "priority", "tags", "timeZone", "reminders", "repeatFlag", "items"], "Update an existing task. Provide only fields to change. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0=none, 1=low, 3=medium, 5=high."),
    "CompleteTask": ("write", ["projectId", "taskId"], "Mark a task as completed."),
    "CreateProject": ("write", ["name", "color", "viewMode", "kind"], "Create a new TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."),
    "UpdateProject": ("write", ["projectId", "name", "color", "viewMode", "kind"], "Update an existing TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."),
    "BatchCreateTasks": ("write", ["tasks"], "Create multiple tasks at once. Each task supports same fields as CreateTask (title required). dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0/1/3/5."),
    # delete
    "DeleteTask": ("delete", ["projectId", "taskId"], "Delete a task from TickTick."),
    "DeleteProject": ("delete", ["projectId"], "Delete a TickTick project."),
}

_SCOPE_NAMES = {
    "read": "ticktick_read",
    "write": "ticktick_write",
    "delete": "ticktick_delete",
}


def _build_help(scope: str) -> str:
    lines = []
    for op, (sc, params, doc) in _OPERATIONS.items():
        if sc != scope:
            continue
        params_str = ", ".join(params) if params else ""
        lines.append(f"  {op}({params_str}) — {doc}")
    return f"{len(lines)} operations available:\n" + "\n".join(lines)


def _parse_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes")
    return bool(val)


def _dispatch(operation: str, scope: str, params_str: str) -> str:
    if operation not in _OPERATIONS:
        return json.dumps({"error": f"Unknown operation: {operation}. Use operation=\"help\" to list available operations."})

    op_scope, _, _ = _OPERATIONS[operation]
    if op_scope != scope:
        return json.dumps({"error": f"{operation} is a {op_scope} operation. Use {_SCOPE_NAMES[op_scope]}() instead."})

    params = json.loads(params_str) if params_str and params_str.strip() else {}
    client = _get_client()

    # ── Read operations ──────────────────────────────────────────────────
    if operation == "GetToday":
        desc = _parse_bool(params.get("desc"), _DEFAULT_DESC)
        descCompact = _parse_bool(params.get("descCompact"), _DEFAULT_DESC_COMPACT)
        slim = _parse_bool(params.get("slim"), _DEFAULT_SLIM)
        tasks = client.get_today_tasks()
        if slim:
            tasks = [_slim_task(t, desc, descCompact) for t in tasks]
        else:
            tasks = _process_tasks(tasks, desc, descCompact)
        return json.dumps(tasks, indent=2, ensure_ascii=False)

    if operation == "GetInbox":
        desc = _parse_bool(params.get("desc"), _DEFAULT_DESC)
        descCompact = _parse_bool(params.get("descCompact"), _DEFAULT_DESC_COMPACT)
        slim = _parse_bool(params.get("slim"), _DEFAULT_SLIM)
        data = client.get_inbox_with_data()
        if "tasks" in data:
            data = dict(data)
            if slim:
                data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
            else:
                data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
        return json.dumps(data, indent=2, ensure_ascii=False)

    if operation == "GetInboxId":
        return json.dumps({"inboxId": client.get_inbox_id()})

    if operation == "ListProjects":
        return json.dumps(client.list_projects(), indent=2, ensure_ascii=False)

    if operation == "GetProject":
        return json.dumps(client.get_project(params["projectId"]), indent=2, ensure_ascii=False)

    if operation == "GetProjectWithData":
        desc = _parse_bool(params.get("desc"), _DEFAULT_DESC)
        descCompact = _parse_bool(params.get("descCompact"), _DEFAULT_DESC_COMPACT)
        slim = _parse_bool(params.get("slim"), _DEFAULT_SLIM)
        data = client.get_project_with_data(params["projectId"])
        if "tasks" in data:
            data = dict(data)
            if slim:
                data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
            else:
                data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
        return json.dumps(data, indent=2, ensure_ascii=False)

    if operation == "GetTask":
        return json.dumps(client.get_task(params["projectId"], params["taskId"]), indent=2, ensure_ascii=False)

    # ── Write operations ─────────────────────────────────────────────────
    if operation == "CreateTask":
        task = _prepare_task(params)
        result = client.create_task(task)
        _verify_response(task, result)
        return json.dumps(result, indent=2, ensure_ascii=False)

    if operation == "UpdateTask":
        if params.get("brief") and params.get("content") is None:
            existing = client.get_task(params["projectId"], params["taskId"])
            params["content"] = existing.get("content") or ""
        task = _prepare_task(params, is_update=True)
        result = client.update_task(params["taskId"], task)
        _verify_response(task, result)
        return json.dumps(result, indent=2, ensure_ascii=False)

    if operation == "CompleteTask":
        client.complete_task(params["projectId"], params["taskId"])
        return f"Task {params['taskId']} marked as completed."

    if operation == "CreateProject":
        proj = _prepare_project(params)
        result = client.create_project(proj)
        _verify_response(proj, result)
        return json.dumps(result, indent=2, ensure_ascii=False)

    if operation == "UpdateProject":
        proj = _prepare_project(params, is_update=True)
        result = client.update_project(params["projectId"], proj)
        _verify_response(proj, result)
        return json.dumps(result, indent=2, ensure_ascii=False)

    if operation == "BatchCreateTasks":
        prepared = [_prepare_task(t) for t in params["tasks"]]
        return json.dumps(client.batch_create_tasks(prepared), indent=2, ensure_ascii=False)

    # ── Delete operations ────────────────────────────────────────────────
    if operation == "DeleteTask":
        client.delete_task(params["projectId"], params["taskId"])
        return f"Task {params['taskId']} deleted."

    if operation == "DeleteProject":
        client.delete_project(params["projectId"])
        return f"Project {params['projectId']} deleted."

    return json.dumps({"error": f"Unhandled operation: {operation}"})


# ── Meta-tools ────────────────────────────────────────────────────────────────


@mcp.tool()
def ticktick_read(operation: str, params: str = "{}") -> str:
    """Query TickTick data (safe, read-only).

    Call with operation="help" to list all available read operations.
    Otherwise pass the operation name and a JSON object with parameters.

    Example: ticktick_read(operation="GetTask", params='{"projectId": "abc", "taskId": "xyz"}')
    """
    if operation == "help":
        return _build_help("read")
    return _dispatch(operation, "read", params)


@mcp.tool()
def ticktick_write(operation: str, params: str = "{}") -> str:
    """Create, update, or complete TickTick resources (non-destructive).

    Call with operation="help" to list all available write operations.
    Otherwise pass the operation name and a JSON object with parameters.

    Example: ticktick_write(operation="CreateTask", params='{"title": "Buy milk"}')
    """
    if operation == "help":
        return _build_help("write")
    return _dispatch(operation, "write", params)


@mcp.tool()
def ticktick_delete(operation: str, params: str = "{}") -> str:
    """Delete TickTick resources (destructive, irreversible).

    Call with operation="help" to list all available delete operations.
    Otherwise pass the operation name and a JSON object with parameters.

    Example: ticktick_delete(operation="DeleteTask", params='{"projectId": "abc", "taskId": "xyz"}')
    """
    if operation == "help":
        return _build_help("delete")
    return _dispatch(operation, "delete", params)
