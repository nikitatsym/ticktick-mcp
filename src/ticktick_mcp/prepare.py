"""Data preparation, validation, and formatting for TickTick tasks and projects."""

import os
import re
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_BRIEF_RE = re.compile(r"<brief>(.*?)</brief>", re.DOTALL)

_BRIEF_MAX = int(os.environ.get("MCP_TICKTICK_BRIEF_MAX", "100"))
_DEFAULT_TZ = os.environ.get("MCP_TICKTICK_TIMEZONE", "")

_SLIM_FIELDS = {"id", "projectId", "title", "status", "priority", "dueDate", "tags", "parentId", "childIds"}

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAIVE_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_HAS_OFFSET_RE = re.compile(r"[+-]\d{2}:?\d{2}$|Z$")

_VALID_PRIORITIES = {0, 1, 3, 5}
_SKIP_VERIFY = {"content", "desc"}
_TASK_API_FIELDS = ("title", "projectId", "content", "desc", "startDate", "dueDate",
                    "isAllDay", "priority", "tags", "timeZone", "reminders", "repeatFlag", "items")
_PROJECT_API_FIELDS = ("name", "color", "viewMode", "kind")


def _extract_brief(task: dict) -> Optional[str]:
    """Extract <brief>...</brief> from content or desc field."""
    for f in ("content", "desc"):
        val = task.get(f)
        if val:
            m = _BRIEF_RE.search(val)
            if m:
                return m.group(1).strip()
    return None


def _slim_task(task: dict) -> dict:
    """Strip task to essential fields for list context."""
    return {k: v for k, v in task.items() if k in _SLIM_FIELDS}


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
    if _BRIEF_MAX == 0:
        return
    if not content or not _BRIEF_RE.search(content):
        raise ValueError(
            "content must contain a <brief>one-line summary</brief> tag. "
            "Either pass the brief parameter or add the tag to content."
        )
    m = _BRIEF_RE.search(content)
    brief = m.group(1).strip() if m else ""
    if len(brief) > _BRIEF_MAX:
        raise ValueError(
            f"<brief> too long: {len(brief)} chars, max {_BRIEF_MAX}. "
            "Keep it to a concise one-liner."
        )


def _validate_timezone(tz: str) -> ZoneInfo:
    """Validate IANA timezone name, return ZoneInfo."""
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        raise ValueError(
            f"Unknown timezone: '{tz}'. Use IANA names like 'Europe/Berlin', 'Asia/Tbilisi'."
        )


def _normalize_date(val: str, field: str, tz: ZoneInfo | None) -> str:
    """Normalize date string using timezone.

    YYYY-MM-DD → midnight, isAllDay. No offset needed.
    YYYY-MM-DDTHH:MM or YYYY-MM-DDTHH:MM:SS → localize with tz, format with computed offset.
    Manual offsets (+HHMM, Z) are rejected.
    """
    if _HAS_OFFSET_RE.search(val):
        raise ValueError(
            f"{field}: manual UTC offsets are not allowed (got '{val}'). "
            "Pass local time + timeZone instead. Example: dueDate='2026-03-15T19:00', timeZone='Europe/Berlin'."
        )
    if _DATE_ONLY_RE.match(val):
        return f"{val}T00:00:00.000+0000"
    if _NAIVE_DT_RE.match(val):
        if tz is None:
            raise ValueError(
                f"{field} has a time component but no timeZone. "
                "Either pass timeZone or set MCP_TICKTICK_TIMEZONE, "
                "or use date-only format (YYYY-MM-DD) for all-day tasks."
            )
        # Pad seconds if missing (HH:MM → HH:MM:SS)
        if len(val) == 16:  # YYYY-MM-DDTHH:MM
            val += ":00"
        dt = datetime.fromisoformat(val).replace(tzinfo=tz)
        offset = dt.strftime("%z")  # e.g. +0100
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.000{offset}")
    raise ValueError(
        f"{field} has invalid format: '{val}'. "
        "Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
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
    isAllDay_explicit = params.get("isAllDay") is not None
    has_date_only = any(
        params.get(f) is not None and _DATE_ONLY_RE.match(str(params[f]))
        for f in ("startDate", "dueDate")
    )
    # Resolve timezone for date normalization
    tz_name = params.get("timeZone") or _DEFAULT_TZ or None
    tz = _validate_timezone(tz_name) if tz_name else None
    for field in ("startDate", "dueDate"):
        if params.get(field) is not None:
            params[field] = _normalize_date(params[field], field, tz)
    if has_date_only and not isAllDay_explicit:
        params["isAllDay"] = True
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
