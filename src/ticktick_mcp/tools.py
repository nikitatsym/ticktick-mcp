"""TickTick tool operations. All public functions are auto-registered as MCP tools."""

import os
from typing import Optional

from .client import TickTickClient
from .prepare import (
    _prepare_project,
    _prepare_task,
    _slim_task,
    _verify_response,
)
from .registry import ROOT, Group, _op

_client: Optional[TickTickClient] = None


def _get_client() -> TickTickClient:
    global _client
    if _client is None:
        _client = TickTickClient(
            os.environ.get("TICKTICK_CLIENT_ID"),
            os.environ.get("TICKTICK_CLIENT_SECRET"),
        )
    return _client


# ── Groups ───────────────────────────────────────────────────────────────────

ticktick_read = Group(
    "ticktick_read",
    "Query TickTick data (safe, read-only).\n\n"
    "Call with operation=\"help\" to list all available read operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: ticktick_read(operation=\"GetTask\", "
    "params='{\"projectId\": \"abc\", \"taskId\": \"xyz\"}')",
)

ticktick_write = Group(
    "ticktick_write",
    "Create, update, or complete TickTick resources (non-destructive).\n\n"
    "Call with operation=\"help\" to list all available write operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: ticktick_write(operation=\"CreateTask\", "
    "params='{\"title\": \"Buy milk\"}')",
)

ticktick_delete = Group(
    "ticktick_delete",
    "Delete TickTick resources (destructive, irreversible).\n\n"
    "Call with operation=\"help\" to list all available delete operations.\n"
    "Otherwise pass the operation name and a JSON object with parameters.\n\n"
    "Example: ticktick_delete(operation=\"DeleteTask\", "
    "params='{\"projectId\": \"abc\", \"taskId\": \"xyz\"}')",
)


# ── Standalone operations ────────────────────────────────────────────────────


@_op(ROOT)
def ticktick_version():
    """Get the TickTick MCP server version."""
    from importlib.metadata import version
    return version("ticktick-mcp")


# ── Read operations ──────────────────────────────────────────────────────────


@_op(ticktick_read)
def get_today():
    """Get all uncompleted tasks due today or earlier (overdue). Same as the 'Today' view in TickTick."""
    return [_slim_task(t) for t in _get_client().get_today_tasks()]


@_op(ticktick_read)
def get_inbox():
    """Get the Inbox project with all its tasks. The Inbox is NOT included in ListProjects."""
    data = _get_client().get_inbox_with_data()
    if "tasks" in data:
        data = dict(data)
        data["tasks"] = [_slim_task(t) for t in data["tasks"]]
    return data


@_op(ticktick_read)
def get_inbox_id():
    """Get the Inbox project ID."""
    return {"inboxId": _get_client().get_inbox_id()}


@_op(ticktick_read)
def list_projects():
    """List all TickTick projects (task lists). Does NOT include the Inbox."""
    return _get_client().list_projects()


@_op(ticktick_read)
def get_project(projectId: str):
    """Get a TickTick project by ID."""
    return _get_client().get_project(projectId)


@_op(ticktick_read)
def get_project_with_data(projectId: str):
    """Get a TickTick project with all its tasks and columns. For inbox tasks, use GetInbox."""
    data = _get_client().get_project_with_data(projectId)
    if "tasks" in data:
        data = dict(data)
        data["tasks"] = [_slim_task(t) for t in data["tasks"]]
    return data


@_op(ticktick_read)
def get_task(projectId: str, taskId: str):
    """Get a specific task by project ID and task ID."""
    return _get_client().get_task(projectId, taskId)


# ── Write operations ─────────────────────────────────────────────────────────


@_op(ticktick_write)
def create_task(
    title: str,
    projectId: Optional[str] = None,
    content: Optional[str] = None,
    desc: Optional[str] = None,
    brief: Optional[str] = None,
    startDate: Optional[str] = None,
    dueDate: Optional[str] = None,
    isAllDay: Optional[bool] = None,
    priority: Optional[int] = None,
    tags: Optional[list[str]] = None,
    timeZone: Optional[str] = None,
    reminders: Optional[list[str]] = None,
    repeatFlag: Optional[str] = None,
    items: Optional[list[dict]] = None,
):
    """Create a new task. If projectId is omitted, goes to Inbox.

    Content must include <brief>summary</brief> tag.
    dueDate/startDate: YYYY-MM-DD (all-day) or YYYY-MM-DDTHH:MM:SS (local time).
    timeZone: IANA name (e.g. 'Europe/Berlin'). Required when using time-of-day.
    priority: 0=none, 1=low, 3=medium, 5=high.
    reminders: iCal triggers e.g. ["TRIGGER:-PT15M"].
    repeatFlag: iCal RRULE e.g. "RRULE:FREQ=WEEKLY".
    """
    task = _prepare_task(locals())
    result = _get_client().create_task(task)
    _verify_response(task, result)
    return result


@_op(ticktick_write)
def update_task(
    taskId: str,
    projectId: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    desc: Optional[str] = None,
    brief: Optional[str] = None,
    startDate: Optional[str] = None,
    dueDate: Optional[str] = None,
    isAllDay: Optional[bool] = None,
    priority: Optional[int] = None,
    tags: Optional[list[str]] = None,
    timeZone: Optional[str] = None,
    reminders: Optional[list[str]] = None,
    repeatFlag: Optional[str] = None,
    items: Optional[list[dict]] = None,
):
    """Update an existing task. Provide only fields to change.

    dueDate/startDate: YYYY-MM-DD (all-day) or YYYY-MM-DDTHH:MM:SS (local time).
    timeZone: IANA name (e.g. 'Europe/Berlin'). Required when using time-of-day.
    priority: 0=none, 1=low, 3=medium, 5=high.
    """
    params = dict(locals())
    if params.get("brief") and params.get("content") is None:
        existing = _get_client().get_task(projectId, taskId)
        params["content"] = existing.get("content") or ""
    task = _prepare_task(params, is_update=True)
    result = _get_client().update_task(taskId, task)
    _verify_response(task, result)
    return result


@_op(ticktick_write)
def complete_task(projectId: str, taskId: str):
    """Mark a task as completed."""
    _get_client().complete_task(projectId, taskId)
    return f"Task {taskId} marked as completed."


@_op(ticktick_write)
def create_project(
    name: str,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
):
    """Create a new TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(locals())
    result = _get_client().create_project(proj)
    _verify_response(proj, result)
    return result


@_op(ticktick_write)
def update_project(
    projectId: str,
    name: Optional[str] = None,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
):
    """Update an existing TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(locals(), is_update=True)
    result = _get_client().update_project(projectId, proj)
    _verify_response(proj, result)
    return result


# ── Delete operations ────────────────────────────────────────────────────────


@_op(ticktick_delete)
def delete_task(projectId: str, taskId: str):
    """Delete a task from TickTick."""
    _get_client().delete_task(projectId, taskId)
    return f"Task {taskId} deleted."


@_op(ticktick_delete)
def delete_project(projectId: str):
    """Delete a TickTick project."""
    _get_client().delete_project(projectId)
    return f"Project {projectId} deleted."
