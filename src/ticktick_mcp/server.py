from __future__ import annotations

import json
import os
import sys
from typing import Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from .client import TickTickClient

mcp = FastMCP("ticktick")

_log = lambda msg: print(f"[ticktick-mcp] {msg}", file=sys.stderr)

client_id = os.environ.get("TICKTICK_CLIENT_ID")
client_secret = os.environ.get("TICKTICK_CLIENT_SECRET")
client = TickTickClient(client_id, client_secret)


def _json(data) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Pydantic models ─────────────────────────────────────────────────────────


class SubtaskItem(BaseModel):
    title: str = Field(description="Subtask title")
    status: int | None = Field(default=None, description="0=normal, 1=completed")
    startDate: str | None = Field(default=None, description="Subtask start date")
    isAllDay: bool | None = Field(default=None, description="All-day subtask")
    sortOrder: int | None = Field(default=None, description="Sort position")
    timeZone: str | None = Field(default=None, description="Time zone")


# ── Inbox ────────────────────────────────────────────────────────────────────


@mcp.tool(description="Get the Inbox project with all its tasks. The Inbox is a special built-in project in TickTick that is NOT included in list_projects. Use this tool whenever you need to see inbox tasks. Returns the inbox project data including all tasks.")
async def get_inbox() -> str:
    try:
        data = await client.get_inbox_with_data()
        return _json(data)
    except Exception as e:
        _log(f"get_inbox failed: {e}")
        raise


@mcp.tool(description='Get the Inbox project ID. Useful when you need the inbox projectId for other operations like complete_task, delete_task, or update_task on inbox tasks. The inbox ID has the format "inbox<userId>" and is unique per user.')
async def get_inbox_id() -> str:
    try:
        inbox_id = await client.get_inbox_id()
        return _json({"inboxId": inbox_id})
    except Exception as e:
        _log(f"get_inbox_id failed: {e}")
        raise


# ── Projects ─────────────────────────────────────────────────────────────────


@mcp.tool(description="List all TickTick projects (task lists). IMPORTANT: This does NOT include the Inbox — use get_inbox to access inbox tasks.")
async def list_projects() -> str:
    try:
        projects = await client.list_projects()
        return _json(projects)
    except Exception as e:
        _log(f"list_projects failed: {e}")
        raise


@mcp.tool(description="Get a TickTick project by ID")
async def get_project(projectId: str) -> str:
    try:
        project = await client.get_project(projectId)
        return _json(project)
    except Exception as e:
        _log(f"get_project failed: {e}")
        raise


@mcp.tool(description="Get a TickTick project with all its tasks and columns. For inbox tasks, use get_inbox instead.")
async def get_project_with_data(projectId: str) -> str:
    try:
        data = await client.get_project_with_data(projectId)
        return _json(data)
    except Exception as e:
        _log(f"get_project_with_data failed: {e}")
        raise


@mcp.tool(description="Create a new TickTick project (task list)")
async def create_project(
    name: str,
    color: str | None = None,
    viewMode: Literal["list", "kanban", "timeline"] | None = None,
    kind: Literal["TASK", "NOTE"] | None = None,
) -> str:
    try:
        params = {"name": name}
        if color is not None:
            params["color"] = color
        if viewMode is not None:
            params["viewMode"] = viewMode
        if kind is not None:
            params["kind"] = kind
        project = await client.create_project(params)
        return _json(project)
    except Exception as e:
        _log(f"create_project failed: {e}")
        raise


@mcp.tool(description="Update an existing TickTick project")
async def update_project(
    projectId: str,
    name: str | None = None,
    color: str | None = None,
    viewMode: Literal["list", "kanban", "timeline"] | None = None,
    kind: Literal["TASK", "NOTE"] | None = None,
) -> str:
    try:
        updates = {}
        if name is not None:
            updates["name"] = name
        if color is not None:
            updates["color"] = color
        if viewMode is not None:
            updates["viewMode"] = viewMode
        if kind is not None:
            updates["kind"] = kind
        project = await client.update_project(projectId, updates)
        return _json(project)
    except Exception as e:
        _log(f"update_project failed: {e}")
        raise


@mcp.tool(description="Delete a TickTick project")
async def delete_project(projectId: str) -> str:
    try:
        await client.delete_project(projectId)
        return f"Project {projectId} deleted."
    except Exception as e:
        _log(f"delete_project failed: {e}")
        raise


# ── Tasks ────────────────────────────────────────────────────────────────────


@mcp.tool(description="Get a specific task by project ID and task ID")
async def get_task(projectId: str, taskId: str) -> str:
    try:
        task = await client.get_task(projectId, taskId)
        return _json(task)
    except Exception as e:
        _log(f"get_task failed: {e}")
        raise


@mcp.tool(description='Create a new task in TickTick. If projectId is omitted, the task goes to Inbox. Supports title, content, dates, priority (0=none, 1=low, 3=medium, 5=high), tags, subtasks (items), reminders, and recurrence (repeatFlag in iCal RRULE format). The response includes the assigned projectId (useful for getting the inbox ID).')
async def create_task(
    title: str,
    projectId: str | None = None,
    content: str | None = None,
    desc: str | None = None,
    startDate: str | None = None,
    dueDate: str | None = None,
    isAllDay: bool | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
    timeZone: str | None = None,
    reminders: list[str] | None = None,
    repeatFlag: str | None = None,
    items: list[SubtaskItem] | None = None,
) -> str:
    try:
        task_data: dict = {"title": title}
        for key, val in [
            ("projectId", projectId), ("content", content), ("desc", desc),
            ("startDate", startDate), ("dueDate", dueDate), ("isAllDay", isAllDay),
            ("priority", priority), ("tags", tags), ("timeZone", timeZone),
            ("reminders", reminders), ("repeatFlag", repeatFlag),
        ]:
            if val is not None:
                task_data[key] = val
        if items is not None:
            task_data["items"] = [item.model_dump(exclude_none=True) for item in items]
        task = await client.create_task(task_data)
        return _json(task)
    except Exception as e:
        _log(f"create_task failed: {e}")
        raise


@mcp.tool(description="Update an existing task. Provide only the fields you want to change.")
async def update_task(
    taskId: str,
    projectId: str,
    title: str | None = None,
    content: str | None = None,
    desc: str | None = None,
    startDate: str | None = None,
    dueDate: str | None = None,
    isAllDay: bool | None = None,
    priority: int | None = None,
    tags: list[str] | None = None,
    timeZone: str | None = None,
    reminders: list[str] | None = None,
    repeatFlag: str | None = None,
    items: list[SubtaskItem] | None = None,
) -> str:
    try:
        updates: dict = {"projectId": projectId}
        for key, val in [
            ("title", title), ("content", content), ("desc", desc),
            ("startDate", startDate), ("dueDate", dueDate), ("isAllDay", isAllDay),
            ("priority", priority), ("tags", tags), ("timeZone", timeZone),
            ("reminders", reminders), ("repeatFlag", repeatFlag),
        ]:
            if val is not None:
                updates[key] = val
        if items is not None:
            updates["items"] = [item.model_dump(exclude_none=True) for item in items]
        task = await client.update_task(taskId, updates)
        return _json(task)
    except Exception as e:
        _log(f"update_task failed: {e}")
        raise


@mcp.tool(description="Mark a task as completed")
async def complete_task(projectId: str, taskId: str) -> str:
    try:
        await client.complete_task(projectId, taskId)
        return f"Task {taskId} marked as completed."
    except Exception as e:
        _log(f"complete_task failed: {e}")
        raise


@mcp.tool(description="Delete a task from TickTick")
async def delete_task(projectId: str, taskId: str) -> str:
    try:
        await client.delete_task(projectId, taskId)
        return f"Task {taskId} deleted."
    except Exception as e:
        _log(f"delete_task failed: {e}")
        raise


@mcp.tool(description="Create multiple tasks at once. Each task object supports the same fields as create_task.")
async def batch_create_tasks(tasks: list[dict]) -> str:
    try:
        result = await client.batch_create_tasks(tasks)
        return _json(result)
    except Exception as e:
        _log(f"batch_create_tasks failed: {e}")
        raise
