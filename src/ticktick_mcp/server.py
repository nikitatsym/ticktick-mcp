import json
import os
import re
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .client import TickTickClient

mcp = FastMCP("ticktick")

_client: Optional[TickTickClient] = None

_BRIEF_RE = re.compile(r"<brief>(.*?)</brief>", re.DOTALL)

_DEFAULT_DESC = os.environ.get("TICKTICK_DESC_DEFAULT", "false").lower() in ("1", "true", "yes")
_DEFAULT_DESC_COMPACT = os.environ.get("TICKTICK_DESC_COMPACT_DEFAULT", "true").lower() in ("1", "true", "yes")
_DEFAULT_SLIM = os.environ.get("TICKTICK_SLIM_DEFAULT", "true").lower() in ("1", "true", "yes")
_REQUIRE_BRIEF = os.environ.get("TICKTICK_REQUIRE_BRIEF", "true").lower() not in ("0", "false", "no")
_BRIEF_MAX_LENGTH = int(os.environ.get("TICKTICK_BRIEF_MAX_LENGTH", "200"))

_SLIM_FIELDS = {"id", "projectId", "title", "status", "priority", "dueDate", "tags", "parentId", "childIds"}


def _get_client() -> TickTickClient:
    global _client
    if _client is None:
        _client = TickTickClient(
            os.environ.get("TICKTICK_CLIENT_ID"),
            os.environ.get("TICKTICK_CLIENT_SECRET"),
        )
    return _client


def _extract_brief(task: dict) -> Optional[str]:
    """Extract <brief>...</brief> from content or desc field."""
    for f in ("content", "desc"):
        val = task.get(f)
        if val:
            m = _BRIEF_RE.search(val)
            if m:
                return m.group(1).strip()
    return None


def _slim_task(task: dict, desc: bool, descCompact: bool) -> dict:
    """Strip task to essential fields for list context."""
    out = {k: v for k, v in task.items() if k in _SLIM_FIELDS}
    if desc:
        if descCompact:
            brief = _extract_brief(task)
            if brief:
                out["brief"] = brief
        else:
            for f in ("content", "desc"):
                if f in task:
                    out[f] = task[f]
    return out


def _process_tasks(tasks: list, desc: bool, descCompact: bool) -> list:
    """Filter description fields from task objects based on desc/descCompact flags."""
    if desc and not descCompact:
        return tasks
    result = []
    for task in tasks:
        task = dict(task)
        if descCompact:
            brief = _extract_brief(task)
            task.pop("content", None)
            task.pop("desc", None)
            if brief:
                task["brief"] = brief
        elif not desc:
            task.pop("content", None)
            task.pop("desc", None)
        result.append(task)
    return result


def _inject_brief(brief: str, content: Optional[str]) -> str:
    """Insert or replace <brief> tag in content."""
    tag = f"<brief>{brief}</brief>"
    if content:
        if _BRIEF_RE.search(content):
            return _BRIEF_RE.sub(tag, content)
        return f"{tag}\n{content}"
    return tag


def _validate_brief(content: Optional[str]) -> None:
    """Raise ValueError if brief requirement is on and content lacks a valid <brief> tag."""
    if not _REQUIRE_BRIEF:
        return
    if not content or not _BRIEF_RE.search(content):
        raise ValueError(
            "content must contain a <brief>one-line summary</brief> tag. "
            "Either pass the brief parameter or add the tag to content."
        )
    m = _BRIEF_RE.search(content)
    brief = m.group(1).strip() if m else ""
    if len(brief) > _BRIEF_MAX_LENGTH:
        raise ValueError(
            f"<brief> too long: {len(brief)} chars, max {_BRIEF_MAX_LENGTH}. "
            "Keep it to a concise one-liner."
        )


# ── Validation & preparation ─────────────────────────────────────────────────

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATETIME_TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)$")
_DATETIME_NO_TZ_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$")

_VALID_PRIORITIES = {0, 1, 3, 5}
_SKIP_VERIFY = {"content", "desc"}
_TASK_API_FIELDS = ("title", "projectId", "content", "desc", "startDate", "dueDate",
                    "isAllDay", "priority", "tags", "timeZone", "reminders", "repeatFlag", "items")
_PROJECT_API_FIELDS = ("name", "color", "viewMode", "kind")


def _normalize_date(val: str, field: str) -> str:
    """Normalize date string. YYYY-MM-DD → midnight UTC, with tz → passthrough, no tz → error."""
    if _DATE_ONLY_RE.match(val):
        return f"{val}T00:00:00.000+0000"
    if _DATETIME_TZ_RE.match(val):
        return val
    if _DATETIME_NO_TZ_RE.match(val):
        raise ValueError(
            f"{field} has datetime without timezone: '{val}'. "
            "Use YYYY-MM-DD for all-day or YYYY-MM-DDTHH:MM:SS±HHMM for specific time."
        )
    raise ValueError(
        f"{field} has invalid format: '{val}'. "
        "Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM."
    )


def _validate_priority(val) -> int:
    """Validate and coerce priority. Allowed: 0 (none), 1 (low), 3 (medium), 5 (high)."""
    try:
        val = int(val)
    except (TypeError, ValueError):
        raise ValueError(f"priority must be 0 (none), 1 (low), 3 (medium), or 5 (high). Got: {val!r}")
    if val not in _VALID_PRIORITIES:
        raise ValueError(f"priority must be 0 (none), 1 (low), 3 (medium), or 5 (high). Got: {val}")
    return val


def _validate_enum(val, field: str, allowed: set) -> str:
    """Validate value is in allowed set."""
    val = str(val)
    if val not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}. Got: {val!r}")
    return val


def _require(params: dict, *keys) -> None:
    """Check required keys are present and not None."""
    missing = [k for k in keys if params.get(k) is None]
    if missing:
        got = [k for k, v in params.items() if v is not None]
        raise ValueError(f"Required: {', '.join(repr(k) for k in missing)}. Got: {got}")


def _prepare_task(params: dict, is_update: bool = False) -> dict:
    """Build a validated, normalized task dict for the API."""
    params = dict(params)
    brief = params.pop("brief", None)
    if brief:
        params["content"] = _inject_brief(brief, params.get("content"))
    content = params.get("content")
    if is_update:
        if content is not None:
            _validate_brief(content)
    else:
        _validate_brief(content)
    for field in ("startDate", "dueDate"):
        if params.get(field) is not None:
            params[field] = _normalize_date(params[field], field)
    if params.get("priority") is not None:
        params["priority"] = _validate_priority(params["priority"])
    if params.get("isAllDay") is not None:
        v = params["isAllDay"]
        params["isAllDay"] = v.lower() in ("true", "1", "yes") if isinstance(v, str) else bool(v)
    if is_update:
        _require(params, "projectId", "taskId")
    else:
        _require(params, "title")
    task = {}
    for key in _TASK_API_FIELDS:
        if params.get(key) is not None:
            task[key] = params[key]
    return task


def _prepare_project(params: dict, is_update: bool = False) -> dict:
    """Build a validated project dict for the API."""
    params = dict(params)
    if params.get("viewMode") is not None:
        _validate_enum(params["viewMode"], "viewMode", {"list", "kanban", "timeline"})
    if params.get("kind") is not None:
        _validate_enum(params["kind"], "kind", {"TASK", "NOTE"})
    if not is_update:
        _require(params, "name")
    proj = {}
    for key in _PROJECT_API_FIELDS:
        if params.get(key) is not None:
            proj[key] = params[key]
    return proj


def _verify_response(sent: dict, received) -> None:
    """Check that all keys we sent are present in the API response."""
    if not isinstance(received, dict):
        return
    for key in sent:
        if key in _SKIP_VERIFY:
            continue
        if key not in received:
            raise ValueError(
                f"API silently dropped '{key}'. The resource was created/updated "
                "but the field was ignored. Check the value format."
            )


# ── Today ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_today(desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    """Get all uncompleted tasks due today or earlier (overdue). Same as the 'Today' view in TickTick. Use desc=False to hide descriptions and save tokens, or descCompact=True to return only the <brief>...</brief> portion of each description."""
    tasks = _get_client().get_today_tasks()
    if slim:
        tasks = [_slim_task(t, desc, descCompact) for t in tasks]
    else:
        tasks = _process_tasks(tasks, desc, descCompact)
    return json.dumps(tasks, indent=2, ensure_ascii=False)


# ── Inbox ────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_inbox(desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    """Get the Inbox project with all its tasks. The Inbox is a special built-in project in TickTick that is NOT included in list_projects. Use this tool whenever you need to see inbox tasks. Use desc=False to hide descriptions, or descCompact=True to return only <brief>...</brief> portions."""
    data = _get_client().get_inbox_with_data()
    if "tasks" in data:
        data = dict(data)
        if slim:
            data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
        else:
            data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
    return json.dumps(data, indent=2, ensure_ascii=False)


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
def get_project_with_data(projectId: str, desc: bool = _DEFAULT_DESC, descCompact: bool = _DEFAULT_DESC_COMPACT, slim: bool = _DEFAULT_SLIM) -> str:
    """Get a TickTick project with all its tasks and columns. For inbox tasks, use get_inbox instead. Use desc=False to hide descriptions, or descCompact=True to return only <brief>...</brief> portions."""
    data = _get_client().get_project_with_data(projectId)
    if "tasks" in data:
        data = dict(data)
        if slim:
            data["tasks"] = [_slim_task(t, desc, descCompact) for t in data["tasks"]]
        else:
            data["tasks"] = _process_tasks(data["tasks"], desc, descCompact)
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def create_project(
    name: str,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """Create a new TickTick project (task list). viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(locals())
    result = _get_client().create_project(proj)
    _verify_response(proj, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
def update_project(
    projectId: str,
    name: Optional[str] = None,
    color: Optional[str] = None,
    viewMode: Optional[str] = None,
    kind: Optional[str] = None,
) -> str:
    """Update an existing TickTick project. viewMode: list, kanban, or timeline. kind: TASK or NOTE."""
    proj = _prepare_project(locals(), is_update=True)
    result = _get_client().update_project(projectId, proj)
    _verify_response(proj, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


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
    """Create a new task in TickTick. If projectId is omitted, the task goes to Inbox. Content must include <brief>summary</brief> tag. brief: short summary stored as <brief> tag inside content (shown in compact list views). priority: 0=none, 1=low, 3=medium, 5=high. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. reminders: list of iCal triggers, e.g. ["TRIGGER:-PT15M"]. repeatFlag: iCal RRULE, e.g. "RRULE:FREQ=WEEKLY". items are subtask/checklist objects with title (required), status (0=normal, 1=completed), startDate, isAllDay, sortOrder, timeZone."""
    task = _prepare_task(locals())
    result = _get_client().create_task(task)
    _verify_response(task, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


@mcp.tool()
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
    """Update an existing task. Provide only the fields you want to change. Content must include <brief>summary</brief> tag. brief: update the short summary stored as <brief> tag inside content. priority: 0=none, 1=low, 3=medium, 5=high. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM."""
    params = dict(locals())
    if params.get("brief") and params.get("content") is None:
        existing = _get_client().get_task(projectId, taskId)
        params["content"] = existing.get("content") or ""
    task = _prepare_task(params, is_update=True)
    result = _get_client().update_task(taskId, task)
    _verify_response(task, result)
    return json.dumps(result, indent=2, ensure_ascii=False)


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
    """Create multiple tasks at once. Each task object supports the same fields as create_task (title is required). Content must include <brief>summary</brief> tag. dueDate/startDate: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS±HHMM. priority: 0=none, 1=low, 3=medium, 5=high."""
    prepared = [_prepare_task(t) for t in tasks]
    return json.dumps(_get_client().batch_create_tasks(prepared), indent=2, ensure_ascii=False)
