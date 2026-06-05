"""TickTick tool operations. All public functions are auto-registered as MCP tools.

Optional parameters default to `cast(T, _UNSET)` so callers can distinguish
"omitted" from "explicit None". The cast keeps mypy strict happy — the visible
annotation is the real type (`str | None`, `list[str]`, ...) while the runtime
default is the sentinel that `_prepare_task` strips first thing.

Brief enforcement is expressed as a runtime cross-field rule (`brief` param OR
`<brief>` tag in `content`), not as a Pydantic-required field, so the
content-only path stays valid. The JSON Schema's `required: ["title"]` reflects
this — the rule lives in the docstring, help bullets, and validation message.
"""

from __future__ import annotations

from typing import Annotated, Any, cast

from pydantic import Field

from .client import TickTickClient
from .prepare import (
    _prepare_project,
    _prepare_task,
    _slim_task,
    _verify_response,
)
from .registry import ROOT, Group, _UNSET, _op
from .types import ProjectDataDict, ProjectDict, SlimTaskDict, TaskDict

_client: TickTickClient | None = None


def _get_client() -> TickTickClient:
    global _client
    if _client is None:
        _client = TickTickClient()
    return _client


def _attach_tz(result: dict[str, Any], tz_meta: Any) -> dict[str, Any]:
    """Splice the wrapper-side timezone echo into a dict result (no-op otherwise)."""
    if tz_meta:
        out = dict(result)
        out["_used_timezone"] = tz_meta
        return out
    return result


# ── Groups ───────────────────────────────────────────────────────────────────

_GROUP_USAGE = (
    "\n\n"
    "operation='help'                        — list ops with parameter names + types.\n"
    "operation='help' params={'search':'X'}  — same, filtered to ops whose name contains X (case-insensitive).\n"
    "operation='schema'                      — JSON Schema for one op. params={'op': 'OpName'} or params={} to list op names.\n"
    "operation='<OpName>' params={...}       — invoke. Params validated strictly: "
    "unknown keys, wrong types, missing required → ValueError with field-level detail."
)

ticktick_read = Group(
    "ticktick_read",
    "Query TickTick data — safe, read-only." + _GROUP_USAGE,
)

ticktick_write = Group(
    "ticktick_write",
    "Create, update, or complete TickTick resources — non-destructive." + _GROUP_USAGE,
)

ticktick_delete = Group(
    "ticktick_delete",
    "Delete TickTick resources — destructive, irreversible." + _GROUP_USAGE,
)


# ── Standalone operation ─────────────────────────────────────────────────────


@_op(ROOT)
def ticktick_version() -> dict[str, Any]:
    """Get the TickTick MCP server version and service status."""
    from importlib.metadata import version
    try:
        _get_client().list_projects()
        service: dict[str, Any] = {"status": "ok"}
    except Exception:
        service = {"status": "error"}
    return {"mcp": version("ticktick-mcp"), "service": service}


# ── Read operations ──────────────────────────────────────────────────────────


@_op(ticktick_read)
def get_today() -> list[SlimTaskDict]:
    """Get all uncompleted tasks due today or earlier (overdue).

    Same as the 'Today' view in TickTick. Tasks are returned in slim form
    (id, projectId, title, status, priority, dueDate, tags, parentId,
    childIds) — call GetTask for the full body of a specific task.
    """
    return [_slim_task(t) for t in _get_client().get_today_tasks()]


@_op(ticktick_read)
def get_inbox() -> ProjectDataDict:
    """Get the Inbox project with all its tasks. The Inbox is NOT included in ListProjects."""
    data = _get_client().get_inbox_with_data()
    if "tasks" in data:
        out: dict[str, Any] = dict(data)
        out["tasks"] = [_slim_task(t) for t in data.get("tasks") or []]
        return cast(ProjectDataDict, out)
    return data


@_op(ticktick_read)
def get_inbox_id() -> dict[str, str]:
    """Get the Inbox project ID."""
    return {"inboxId": _get_client().get_inbox_id()}


@_op(ticktick_read)
def list_projects() -> list[ProjectDict]:
    """List all TickTick projects (task lists). Does NOT include the Inbox — use GetInbox for that."""
    return _get_client().list_projects()


@_op(ticktick_read)
def get_project(
    projectId: Annotated[str, Field(description="Project ID returned by ListProjects.")],
) -> ProjectDict:
    """Get a TickTick project by ID."""
    return _get_client().get_project(projectId)


@_op(ticktick_read)
def get_project_with_data(
    projectId: Annotated[str, Field(description="Project ID returned by ListProjects.")],
) -> ProjectDataDict:
    """Get a TickTick project with all its tasks and columns. For inbox tasks, use GetInbox."""
    data = _get_client().get_project_with_data(projectId)
    if "tasks" in data:
        out: dict[str, Any] = dict(data)
        out["tasks"] = [_slim_task(t) for t in data.get("tasks") or []]
        return cast(ProjectDataDict, out)
    return data


@_op(ticktick_read)
def get_task(
    projectId: Annotated[str, Field(description="Project ID — Inbox tasks use the inbox id from GetInboxId.")],
    taskId: Annotated[str, Field(description="Task ID.")],
) -> TaskDict:
    """Get a specific task by project ID and task ID."""
    return _get_client().get_task(projectId, taskId)


# ── Write operations ─────────────────────────────────────────────────────────


@_op(ticktick_write)
def create_task(
    title: Annotated[str, Field(description="Task title.")],
    projectId: Annotated[str | None, Field(description="Target project ID. Omit to put the task in Inbox.")] = cast(str | None, _UNSET),
    content: Annotated[str | None, Field(description=(
        "Long-form body. Must contain <brief>…</brief> if you don't pass the 'brief' parameter "
        "(or set MCP_TICKTICK_BRIEF_MAX=0 to disable the rule entirely)."
    ))] = cast(str | None, _UNSET),
    desc: Annotated[str | None, Field(description="Short note for checklist-style tasks (TickTick 'Notes' field).")] = cast(str | None, _UNSET),
    brief: Annotated[str | None, Field(description=(
        "One-liner stored as <brief>summary</brief> inside content. "
        "Required (or include <brief>…</brief> directly in content) when MCP_TICKTICK_BRIEF_MAX > 0. "
        "Shown in slim list views."
    ))] = cast(str | None, _UNSET),
    startDate: Annotated[str | None, Field(description=(
        "YYYY-MM-DD (all-day) or YYYY-MM-DDTHH:MM[:SS] (local time). "
        "Manual offsets like '+0300' / 'Z' are rejected."
    ))] = cast(str | None, _UNSET),
    dueDate: Annotated[str | None, Field(description=(
        "YYYY-MM-DD (all-day) or YYYY-MM-DDTHH:MM[:SS] (local time). "
        "Manual offsets like '+0300' / 'Z' are rejected."
    ))] = cast(str | None, _UNSET),
    isAllDay: Annotated[bool | None, Field(description=(
        "Whether the task is all-day. Inferred from date shape if omitted. "
        "When reminders are present, this MUST be set (explicit or inferable) — "
        "reminder trigger format depends on the mode (PT9H for all-day, -PT5M for timed)."
    ))] = cast(bool | None, _UNSET),
    priority: Annotated[int | None, Field(description="0 = none, 1 = low, 3 = medium, 5 = high.")] = cast(int | None, _UNSET),
    tags: Annotated[list[str] | None, Field(description="Tag names (auto-created if missing).")] = cast(list[str] | None, _UNSET),
    timeZone: Annotated[str | None, Field(description=(
        "IANA name (e.g. 'Europe/Berlin'). REQUIRED when startDate/dueDate has a time. "
        "Falls back to MCP_TICKTICK_TIMEZONE env var (echoed in result as _used_timezone)."
    ))] = cast(str | None, _UNSET),
    reminders: Annotated[list[str] | None, Field(description=(
        "iCal TRIGGER durations. All-day: positive offsets from midnight, "
        "e.g. ['TRIGGER:PT9H'] = 9am. Timed: negative offsets from event, "
        "e.g. ['TRIGGER:-PT5M'] = 5min before. Compound forms (-P1DT2H) ok."
    ))] = cast(list[str] | None, _UNSET),
    repeatFlag: Annotated[str | None, Field(description="iCal RRULE, e.g. 'RRULE:FREQ=WEEKLY'.")] = cast(str | None, _UNSET),
    items: Annotated[list[dict[str, Any]] | None, Field(description="Checklist sub-items, each {'title': str, 'status': 0|2}.")] = cast(list[dict[str, Any]] | None, _UNSET),
) -> dict[str, Any]:
    """Create a new task. Requires brief or <brief>…</brief> in content (unless MCP_TICKTICK_BRIEF_MAX=0).

    When you pass a time of day (HH:MM), pass timeZone explicitly — falls back to
    MCP_TICKTICK_TIMEZONE env var, which can surprise. The zone actually used
    is echoed back as _used_timezone in the result so you can verify.

    Reminders require isAllDay to be set or inferable. Triggers must match the
    mode: PT9H (all-day) vs -PT5M (timed). The wrapper validates fail-fast.
    """
    task, tz_meta = _prepare_task(dict(locals()))
    result = _get_client().create_task(task)
    _verify_response(task, result)
    return _attach_tz(dict(result), tz_meta)


@_op(ticktick_write)
def update_task(
    taskId: Annotated[str, Field(description="Task ID returned by GetTask / GetProjectWithData.")],
    projectId: Annotated[str, Field(description="Project ID of the task (Inbox tasks: the inbox id).")],
    title: Annotated[str | None, Field(description="New title.")] = cast(str | None, _UNSET),
    content: Annotated[str | None, Field(description=(
        "Replacement body. If passing brief without content, the existing body is fetched "
        "and only the <brief> tag is rewritten (your text is preserved). To clear content, "
        "explicit-null is not supported yet — pass a single space or new content with <brief>."
    ))] = cast(str | None, _UNSET),
    desc: Annotated[str | None, Field(description="Replacement 'Notes' field.")] = cast(str | None, _UNSET),
    brief: Annotated[str | None, Field(description=(
        "Replacement one-liner. Passed alone (no content) triggers a fetch-merge: "
        "the existing body is preserved and only <brief>…</brief> is rewritten."
    ))] = cast(str | None, _UNSET),
    startDate: Annotated[str | None, Field(description="YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS]. Manual offsets rejected.")] = cast(str | None, _UNSET),
    dueDate: Annotated[str | None, Field(description="YYYY-MM-DD or YYYY-MM-DDTHH:MM[:SS]. Manual offsets rejected.")] = cast(str | None, _UNSET),
    isAllDay: Annotated[bool | None, Field(description=(
        "MUST be passed explicitly when changing reminders/startDate/dueDate — "
        "the API silently drops it otherwise. PT9H for all-day, -PT5M for timed."
    ))] = cast(bool | None, _UNSET),
    priority: Annotated[int | None, Field(description="0 = none, 1 = low, 3 = medium, 5 = high.")] = cast(int | None, _UNSET),
    tags: Annotated[list[str] | None, Field(description="Replacement tag list.")] = cast(list[str] | None, _UNSET),
    timeZone: Annotated[str | None, Field(description=(
        "IANA name. REQUIRED when startDate/dueDate has a time. "
        "Falls back to MCP_TICKTICK_TIMEZONE env var (echoed as _used_timezone)."
    ))] = cast(str | None, _UNSET),
    reminders: Annotated[list[str] | None, Field(description=(
        "Replacement TRIGGER list. PT9H (positive) for all-day, -PT5M (negative) for timed. "
        "isAllDay must be passed explicitly alongside this to avoid silent drop."
    ))] = cast(list[str] | None, _UNSET),
    repeatFlag: Annotated[str | None, Field(description="iCal RRULE, e.g. 'RRULE:FREQ=WEEKLY'.")] = cast(str | None, _UNSET),
    items: Annotated[list[dict[str, Any]] | None, Field(description="Replacement checklist sub-items.")] = cast(list[dict[str, Any]] | None, _UNSET),
) -> dict[str, Any]:
    """Update an existing task. Provide only the fields to change.

    Passing brief without content fetches the existing task and updates only the
    <brief> tag — your body text is preserved.

    When changing reminders/startDate/dueDate, isAllDay MUST be passed explicitly:
    the API silently drops it otherwise, and reminder trigger format depends on it.

    Time-of-day on startDate/dueDate requires timeZone. Falls back to
    MCP_TICKTICK_TIMEZONE — the zone actually used is echoed as _used_timezone.
    """
    params = dict(locals())

    # Brief-only update: fetch existing content so _prepare_task's brief
    # injection rewrites the tag in place instead of clobbering the body.
    # Condition: brief was passed (non-_UNSET, non-None, non-empty) AND
    # content was not passed. brief="" is rejected later in _validate_brief.
    if (
        params.get("brief") is not _UNSET
        and params.get("brief") is not None
        and params.get("brief") != ""
        and params.get("content") is _UNSET
    ):
        existing = _get_client().get_task(projectId, taskId)
        params["content"] = existing.get("content") or ""

    task, tz_meta = _prepare_task(params, is_update=True)
    result = _get_client().update_task(taskId, task)
    _verify_response(task, result)
    return _attach_tz(dict(result), tz_meta)


@_op(ticktick_write)
def complete_task(
    projectId: Annotated[str, Field(description="Project ID of the task (Inbox tasks: the inbox id).")],
    taskId: Annotated[str, Field(description="Task ID.")],
) -> str:
    """Mark a task as completed."""
    _get_client().complete_task(projectId, taskId)
    return f"Task {taskId} marked as completed."


@_op(ticktick_write)
def create_project(
    name: Annotated[str, Field(description="Project name.")],
    color: Annotated[str | None, Field(description="Hex color, e.g. '#FF0000'.")] = cast(str | None, _UNSET),
    viewMode: Annotated[str | None, Field(description="One of: 'list', 'kanban', 'timeline'.")] = cast(str | None, _UNSET),
    kind: Annotated[str | None, Field(description="One of: 'TASK', 'NOTE'.")] = cast(str | None, _UNSET),
) -> ProjectDict:
    """Create a new TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(dict(locals()))
    result = _get_client().create_project(proj)
    _verify_response(proj, result)
    return result


@_op(ticktick_write)
def update_project(
    projectId: Annotated[str, Field(description="Project ID.")],
    name: Annotated[str | None, Field(description="New project name.")] = cast(str | None, _UNSET),
    color: Annotated[str | None, Field(description="Hex color, e.g. '#FF0000'.")] = cast(str | None, _UNSET),
    viewMode: Annotated[str | None, Field(description="One of: 'list', 'kanban', 'timeline'.")] = cast(str | None, _UNSET),
    kind: Annotated[str | None, Field(description="One of: 'TASK', 'NOTE'.")] = cast(str | None, _UNSET),
) -> ProjectDict:
    """Update an existing TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(dict(locals()), is_update=True)
    result = _get_client().update_project(projectId, proj)
    _verify_response(proj, result)
    return result


# ── Delete operations ────────────────────────────────────────────────────────


@_op(ticktick_delete)
def delete_task(
    projectId: Annotated[str, Field(description="Project ID of the task (Inbox tasks: the inbox id).")],
    taskId: Annotated[str, Field(description="Task ID.")],
) -> str:
    """Delete a task from TickTick."""
    _get_client().delete_task(projectId, taskId)
    return f"Task {taskId} deleted."


@_op(ticktick_delete)
def delete_project(
    projectId: Annotated[str, Field(description="Project ID.")],
) -> str:
    """Delete a TickTick project."""
    _get_client().delete_project(projectId)
    return f"Project {projectId} deleted."
