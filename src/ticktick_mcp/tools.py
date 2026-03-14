"""TickTick tool operations. All public functions are auto-registered as MCP tools."""

import json
import os
from typing import Optional

from .client import TickTickClient
from .prepare import (
    _DEFAULT_DESC,
    _DEFAULT_DESC_COMPACT,
    _DEFAULT_SLIM,
    _prepare_project,
    _prepare_task,
    _process_tasks,
    _slim_task,
    _verify_response,
)

_client: Optional[TickTickClient] = None


def _get_client() -> TickTickClient:
    global _client
    if _client is None:
        _client = TickTickClient(
            os.environ.get("TICKTICK_CLIENT_ID"),
            os.environ.get("TICKTICK_CLIENT_SECRET"),
        )
    return _client


def _op(group: str, *, desc: str):
    def decorator(fn):
        fn._mcp_group = group
        fn._mcp_desc = desc
        return fn
    return decorator


# ── Read operations ──────────────────────────────────────────────────────────


@_op("ticktick_read", desc="Get all uncompleted tasks due today or earlier (overdue). Same as the 'Today' view in TickTick.")
def get_today(desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    tasks = _get_client().get_today_tasks()
    if slim:
        tasks = [_slim_task(t, desc, descCompact) for t in tasks]
    else:
        tasks = _process_tasks(tasks, desc, descCompact)
    return json.dumps(tasks, indent=2, ensure_ascii=False)


@_op("ticktick_read", desc="Get the Inbox project with all its tasks. The Inbox is NOT included in ListProjects.")
def get_inbox(desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    data = _get_client().get_inbox_with_data()
    if "tasks" in data:
        data = dict(data)
        if slim:
            data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
        else:
            data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
    return json.dumps(data, indent=2, ensure_ascii=False)


@_op("ticktick_read", desc="Get the Inbox project ID.")
def get_inbox_id() -> str:
    return json.dumps({"inboxId": _get_client().get_inbox_id()})


@_op("ticktick_read", desc="List all TickTick projects (task lists). Does NOT include the Inbox.")
def list_projects() -> str:
    return json.dumps(_get_client().list_projects(), indent=2, ensure_ascii=False)


@_op("ticktick_read", desc="Get a TickTick project by ID.")
def get_project(projectId: str) -> str:
    return json.dumps(_get_client().get_project(projectId), indent=2, ensure_ascii=False)


@_op("ticktick_read", desc="Get a TickTick project with all its tasks and columns. For inbox tasks, use GetInbox.")
def get_project_with_data(projectId: str, desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    data = _get_client().get_project_with_data(projectId)
    if "tasks" in data:
        data = dict(data)
        if slim:
            data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
        else:
            data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
    return json.dumps(data, indent=2, ensure_ascii=False)


@_op("ticktick_read", desc="Get a specific task by project ID and task ID.")
def get_task(projectId: str, taskId: str) -> str:
    return json.dumps(_get_client().get_task(projectId, taskId), indent=2, ensure_ascii=False)


# ── Write operations ─────────────────────────────────────────────────────────


@_op("ticktick_write", desc="Create a new task. If projectId is omitted, goes to Inbox. Content must include <brief>summary</brief> tag. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0=none, 1=low, 3=medium, 5=high. reminders: iCal triggers e.g. [\"TRIGGER:-PT15M\"]. repeatFlag: iCal RRULE e.g. \"RRULE:FREQ=WEEKLY\".")
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
) -> str:
    task = _prepare_task(locals())
    result = _get_client().create_task(task)
    _verify_response(task, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


@_op("ticktick_write", desc="Update an existing task. Provide only fields to change. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0=none, 1=low, 3=medium, 5=high.")
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
) -> str:
    params = dict(locals())
    if params.get("brief") and params.get("content") is None:
        existing = _get_client().get_task(projectId, taskId)
        params["content"] = existing.get("content") or ""
    task = _prepare_task(params, is_update=True)
    result = _get_client().update_task(taskId, task)
    _verify_response(task, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


@_op("ticktick_write", desc="Mark a task as completed.")
def complete_task(projectId: str, taskId: str) -> str:
    _get_client().complete_task(projectId, taskId)
    return f"Task {taskId} marked as completed."


@_op("ticktick_write", desc="Create a new TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE.")
def create_project(
    name: str,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    proj = _prepare_project(locals())
    result = _get_client().create_project(proj)
    _verify_response(proj, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


@_op("ticktick_write", desc="Update an existing TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE.")
def update_project(
    projectId: str,
    name: Optional[str] = None,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    proj = _prepare_project(locals(), is_update=True)
    result = _get_client().update_project(projectId, proj)
    _verify_response(proj, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


# ── Delete operations ────────────────────────────────────────────────────────


@_op("ticktick_delete", desc="Delete a task from TickTick.")
def delete_task(projectId: str, taskId: str) -> str:
    _get_client().delete_task(projectId, taskId)
    return f"Task {taskId} deleted."


@_op("ticktick_delete", desc="Delete a TickTick project.")
def delete_project(projectId: str) -> str:
    _get_client().delete_project(projectId)
    return f"Project {projectId} deleted."
