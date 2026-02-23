import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .client import TickTickClient

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


# ── Today ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_today() -> str:
    """Get all uncompleted tasks due today or earlier (overdue). This is the same as the 'Today' view in the TickTick app — shows everything that needs attention now."""
    return json.dumps(_get_client().get_today_tasks(), indent=2, ensure_ascii=False)


# ── Inbox ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inbox() -> str:
    """Get the Inbox project with all its tasks. The Inbox is a special built-in project in TickTick that is NOT included in list_projects. Use this tool whenever you need to see inbox tasks."""
    return json.dumps(_get_client().get_inbox_with_data(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_inbox_id() -> str:
    """Get the Inbox project ID. Useful when you need the inbox projectId for other operations like complete_task, delete_task, or update_task on inbox tasks."""
    return json.dumps({"inboxId": _get_client().get_inbox_id()})


# ── Projects ─────────────────────────────────────────────────────────────────

@mcp.tool()
def list_projects() -> str:
    """List all TickTick projects (task lists). IMPORTANT: This does NOT include the Inbox — use get_inbox to access inbox tasks."""
    return json.dumps(_get_client().list_projects(), indent=2, ensure_ascii=False)


@mcp.tool()
def get_project(projectId: str) -> str:
    """Get a TickTick project by ID."""
    return json.dumps(_get_client().get_project(projectId), indent=2, ensure_ascii=False)


@mcp.tool()
def get_project_with_data(projectId: str) -> str:
    """Get a TickTick project with all its tasks and columns. For inbox tasks, use get_inbox instead."""
    return json.dumps(_get_client().get_project_with_data(projectId), indent=2, ensure_ascii=False)


@mcp.tool()
def create_project(
    name: str,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """Create a new TickTick project (task list). viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    params = {"name": name}
    if color is not None:
        params["color"] = color
    if viewMode is not None:
        params["viewMode"] = viewMode
    if kind is not None:
        params["kind"] = kind
    return json.dumps(_get_client().create_project(params), indent=2, ensure_ascii=False)


@mcp.tool()
def update_project(
    projectId: str,
    name: Optional[str] = None,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """Update an existing TickTick project."""
    updates = {}
    if name is not None:
        updates["name"] = name
    if color is not None:
        updates["color"] = color
    if viewMode is not None:
        updates["viewMode"] = viewMode
    if kind is not None:
        updates["kind"] = kind
    return json.dumps(_get_client().update_project(projectId, updates), indent=2, ensure_ascii=False)


@mcp.tool()
def delete_project(projectId: str) -> str:
    """Delete a TickTick project."""
    _get_client().delete_project(projectId)
    return f"Project {projectId} deleted."


# ── Tasks ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_task(projectId: str, taskId: str) -> str:
    """Get a specific task by project ID and task ID."""
    return json.dumps(_get_client().get_task(projectId, taskId), indent=2, ensure_ascii=False)


@mcp.tool()
def create_task(
    title: str,
    projectId: Optional[str] = None,
    content: Optional[str] = None,
    desc: Optional[str] = None,
    startDate: Optional[str] = None,
    dueDate: Optional[str] = None,
    isAllDay: Optional[bool] = None,
    priority: Optional[int] = None,
    tags: Optional[list[str]] = None,
    timeZone: Optional[str] = None,
    reminders: Optional[list[str]] = None,
    repeatFlag: Optional[str] = None,
    items: Optional[list[dict]] = None,
) -> str:
    """Create a new task in TickTick. If projectId is omitted, the task goes to Inbox. priority: 0=none, 1=low, 3=medium, 5=high. startDate/dueDate in ISO 8601 format. reminders in iCal trigger format. repeatFlag in iCal RRULE format. items are subtask/checklist objects with title (required), status (0=normal, 1=completed), startDate, isAllDay, sortOrder, timeZone."""
    task: dict = {"title": title}
    for key in ("projectId", "content", "desc", "startDate", "dueDate", "isAllDay",
                "priority", "tags", "timeZone", "reminders", "repeatFlag", "items"):
        val = locals()[key]
        if val is not None:
            task[key] = val
    return json.dumps(_get_client().create_task(task), indent=2, ensure_ascii=False)


@mcp.tool()
def update_task(
    taskId: str,
    projectId: str,
    title: Optional[str] = None,
    content: Optional[str] = None,
    desc: Optional[str] = None,
    startDate: Optional[str] = None,
    dueDate: Optional[str] = None,
    isAllDay: Optional[bool] = None,
    priority: Optional[int] = None,
    tags: Optional[list[str]] = None,
    timeZone: Optional[str] = None,
    reminders: Optional[list[str]] = None,
    repeatFlag: Optional[str] = None,
    items: Optional[list[dict]] = None,
) -> str:
    """Update an existing task. Provide only the fields you want to change."""
    updates: dict = {"projectId": projectId}
    for key in ("title", "content", "desc", "startDate", "dueDate", "isAllDay",
                "priority", "tags", "timeZone", "reminders", "repeatFlag", "items"):
        val = locals()[key]
        if val is not None:
            updates[key] = val
    return json.dumps(_get_client().update_task(taskId, updates), indent=2, ensure_ascii=False)


@mcp.tool()
def complete_task(projectId: str, taskId: str) -> str:
    """Mark a task as completed."""
    _get_client().complete_task(projectId, taskId)
    return f"Task {taskId} marked as completed."


@mcp.tool()
def delete_task(projectId: str, taskId: str) -> str:
    """Delete a task from TickTick."""
    _get_client().delete_task(projectId, taskId)
    return f"Task {taskId} deleted."


@mcp.tool()
def batch_create_tasks(tasks: list[dict]) -> str:
    """Create multiple tasks at once. Each task object supports the same fields as create_task (title is required)."""
    return json.dumps(_get_client().batch_create_tasks(tasks), indent=2, ensure_ascii=False)
