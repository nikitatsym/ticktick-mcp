"""Data preparation, validation, and formatting for TickTick tasks and projects.

The first line of `_prepare_task`/`_prepare_project` strips `_UNSET` from the
incoming dict so every existing `is not None` check sees "key absent" instead
of "sentinel present." This lets us keep the v1-shape payload loop unchanged
while adopting the omitted-vs-cleared semantics on the public surface.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .config import get_settings, system_timezone
from .registry import _UNSET
from .types import SlimTaskDict, TaskDict, TzMeta

_BRIEF_RE = re.compile(r"<brief>(.*?)</brief>", re.DOTALL)

_SLIM_FIELDS = {
    "id", "projectId", "title", "status", "priority",
    "dueDate", "tags", "parentId", "childIds",
}

_DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_NAIVE_DT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?$")
_HAS_OFFSET_RE = re.compile(r"[+-]\d{2}:?\d{2}$|Z$")

# Compound iCal duration. Outer optional `T` so day-only forms like "P1D" are
# accepted; inner H/M/S each independently optional. The follow-up "any digit"
# assertion in `_validate_reminders` rejects bare `P` / `PT` with no number.
_TRIGGER_RE = re.compile(r"^TRIGGER:-?P(?:\d+D)?(?:T(?:\d+H)?(?:\d+M)?(?:\d+S)?)?$")
_TRIGGER_HAS_DIGIT_RE = re.compile(r"\d")

_VALID_PRIORITIES = {0, 1, 3, 5}
_SKIP_VERIFY = {"content", "desc"}
_TASK_API_FIELDS = (
    "title", "projectId", "content", "desc", "startDate", "dueDate",
    "isAllDay", "priority", "tags", "timeZone", "reminders", "repeatFlag", "items",
)
_PROJECT_API_FIELDS = ("name", "color", "viewMode", "kind")


# ── Brief tag ────────────────────────────────────────────────────────────────


def _extract_brief(task: TaskDict) -> str | None:
    """Extract <brief>...</brief> from content or desc field."""
    for val in (task.get("content"), task.get("desc")):
        if val:
            m = _BRIEF_RE.search(val)
            if m:
                return m.group(1).strip()
    return None


def _slim_task(task: TaskDict) -> SlimTaskDict:
    """Strip task to essential fields for list context."""
    return cast(SlimTaskDict, {k: v for k, v in task.items() if k in _SLIM_FIELDS})


def _inject_brief(brief: str, content: str | None) -> str:
    """Insert or replace <brief> tag in content."""
    tag = f"<brief>{brief}</brief>"
    if content:
        if _BRIEF_RE.search(content):
            return _BRIEF_RE.sub(tag, content)
        return f"{tag}\n{content}"
    return tag


def _validate_brief(content: str | None, brief_param: str | None = None) -> None:
    """Raise ValueError if the brief requirement is on and neither source carries one.

    Two sources are valid: an explicit `brief` parameter OR a `<brief>…</brief>`
    tag already inside `content`. JSON Schema lists only `title` as required;
    this runtime check enforces the cross-field rule that the schema can't.

    `brief_param=""` (empty string) is rejected here so callers don't end up
    with a `<brief></brief>` tag silently accepted by the regex.
    """
    brief_max = get_settings().mcp_ticktick_brief_max
    if brief_max == 0:
        return

    if brief_param is not None:
        if brief_param == "":
            raise ValueError(
                "brief parameter must be non-empty; pass None to omit, or pass "
                "content containing <brief>…</brief> to bypass the parameter path."
            )
        if len(brief_param) > brief_max:
            raise ValueError(
                f"brief too long: {len(brief_param)} chars, max {brief_max}. "
                "Keep it to a concise one-liner."
            )
        return

    if not content or not _BRIEF_RE.search(content):
        raise ValueError(
            "Pass the 'brief' parameter (one-liner stored as <brief>summary</brief>) "
            "or include <brief>…</brief> directly in 'content'. "
            "Disable with MCP_TICKTICK_BRIEF_MAX=0. "
            "Call operation='help' or operation='schema' for the full spec."
        )
    m = _BRIEF_RE.search(content)
    brief = m.group(1).strip() if m else ""
    if len(brief) > brief_max:
        raise ValueError(
            f"<brief> too long: {len(brief)} chars, max {brief_max}. "
            "Keep it to a concise one-liner."
        )


# ── Timezones and dates ──────────────────────────────────────────────────────


def _validate_timezone(tz: str) -> ZoneInfo:
    """Validate IANA timezone name, return ZoneInfo."""
    try:
        return ZoneInfo(tz)
    except (ZoneInfoNotFoundError, KeyError, ValueError):
        raise ValueError(
            f"Unknown timezone: '{tz}'. Use IANA names like 'Europe/Berlin', 'Asia/Tbilisi'."
        )


def _normalize_date(val: str, field: str, tz: ZoneInfo | None) -> str:
    """Normalize a date string with the given timezone.

    YYYY-MM-DD → midnight UTC (all-day).
    YYYY-MM-DDTHH:MM[:SS] → localize with `tz`, format with computed offset.
    Manual offsets (+HHMM, Z) are rejected.
    """
    if _HAS_OFFSET_RE.search(val):
        raise ValueError(
            f"{field}: manual UTC offsets are not allowed (got '{val}'). "
            "Pass local time + timeZone instead. "
            "Example: dueDate='2026-03-15T19:00', timeZone='Europe/Berlin'."
        )
    if _DATE_ONLY_RE.match(val):
        return f"{val}T00:00:00.000+0000"
    if _NAIVE_DT_RE.match(val):
        if tz is None:
            sys_tz = system_timezone()
            hint = (
                f" System timezone is {sys_tz!r} — likely the right answer, but confirm with the user."
                if sys_tz
                else ""
            )
            raise ValueError(
                f"{field} has a time component but no timeZone. "
                "Either pass timeZone or set MCP_TICKTICK_TIMEZONE, "
                "or use date-only format (YYYY-MM-DD) for all-day tasks."
                + hint
            )
        if len(val) == 16:  # YYYY-MM-DDTHH:MM
            val += ":00"
        dt = datetime.fromisoformat(val).replace(tzinfo=tz)
        offset = dt.strftime("%z")
        return dt.strftime(f"%Y-%m-%dT%H:%M:%S.000{offset}")
    raise ValueError(
        f"{field} has invalid format: '{val}'. "
        "Expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS."
    )


# ── Enums and reminders ──────────────────────────────────────────────────────


def _validate_priority(val: Any) -> int:
    """Validate and coerce priority. Allowed: 0 (none), 1 (low), 3 (medium), 5 (high)."""
    try:
        coerced = int(val)
    except (TypeError, ValueError):
        raise ValueError(
            f"priority must be 0 (none), 1 (low), 3 (medium), or 5 (high). Got: {val!r}"
        )
    if coerced not in _VALID_PRIORITIES:
        raise ValueError(
            f"priority must be 0 (none), 1 (low), 3 (medium), or 5 (high). Got: {coerced}"
        )
    return coerced


def _validate_enum(val: Any, field: str, allowed: set[str]) -> str:
    """Validate value is in allowed set, returning the str form."""
    s = str(val)
    if s not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}. Got: {s!r}")
    return s


def _validate_reminders(triggers: list[str], is_all_day: bool) -> None:
    """Validate iCal-duration TRIGGER strings against the resolved isAllDay mode.

    All-day tasks use positive offsets from midnight (e.g. `PT9H` = 9am);
    timed tasks use negative offsets from the event (e.g. `-PT5M` = 5min
    before). The API silently accepts the wrong shape — this check fails
    fast so the agent can correct before a write hits the wire.
    """
    for t in triggers:
        if not isinstance(t, str):
            raise TypeError(
                f"reminders must be a list of iCal TRIGGER strings. Got: {t!r}"
            )
        if not _TRIGGER_RE.match(t) or not _TRIGGER_HAS_DIGIT_RE.search(t):
            raise ValueError(
                f"Invalid reminder trigger format: {t!r}. "
                "Expected iCal duration like 'TRIGGER:PT9H' (all-day, 9am from "
                "midnight) or 'TRIGGER:-PT5M' (timed, 5min before event). "
                "Compound forms like 'TRIGGER:-P1DT2H' are accepted."
            )
        is_negative = t.startswith("TRIGGER:-")
        if is_all_day and is_negative:
            raise ValueError(
                f"All-day tasks use positive offsets from midnight "
                f"(e.g. PT9H = 9am). Got '{t}' (negative)."
            )
        if not is_all_day and not is_negative:
            raise ValueError(
                f"Timed tasks use negative offsets from the event "
                f"(e.g. -PT5M = 5min before). Got '{t}' (positive)."
            )


# ── Task & project payload assembly ──────────────────────────────────────────


_REMINDER_TRIGGERING_FIELDS = ("reminders", "startDate", "dueDate")


def _has_date_only(params: dict[str, Any], field: str) -> bool:
    val = params.get(field)
    return isinstance(val, str) and bool(_DATE_ONLY_RE.match(val))


def _has_time_of_day(params: dict[str, Any], field: str) -> bool:
    val = params.get(field)
    return isinstance(val, str) and bool(_NAIVE_DT_RE.match(val))


def _coerce_bool(v: Any) -> bool:
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _prepare_task(
    params: dict[str, Any],
    is_update: bool = False,
) -> tuple[dict[str, Any], TzMeta | None]:
    """Build (validated task payload, optional timezone-echo metadata).

    Returns the task dict ready for the TickTick API, paired with `tz_meta`
    that describes which timezone was actually used (and whether it came from
    a `timeZone` param or the `MCP_TICKTICK_TIMEZONE` fallback). The wrapper
    surfaces `tz_meta` in the API response so the agent can verify the zone
    it just wrote under — closes the silent-fallback failure mode.
    """
    # 1. Strip the _UNSET sentinel so existing `is not None` checks below
    #    correctly see "key absent" for omitted params.
    params = {k: v for k, v in params.items() if v is not _UNSET}

    brief_param = params.pop("brief", None)

    # Brief-only update: caller passed brief without content. Fetch existing
    # content and let _inject_brief replace just the tag, preserving the body.
    # The actual fetch happens in tools.py (it has the client); here we just
    # surface enough info via the params keys for that branch to apply.
    if brief_param is not None and brief_param != "":
        params["content"] = _inject_brief(brief_param, params.get("content"))

    content = params.get("content")
    if is_update:
        # Validate brief only when content is being changed OR brief was passed.
        if content is not None or brief_param is not None:
            _validate_brief(content, brief_param=brief_param)
    else:
        _validate_brief(content, brief_param=brief_param)

    # 2. Resolve timezone (param > env fallback). Track its source for echo.
    explicit_tz = params.get("timeZone")
    settings = get_settings()
    env_tz = settings.mcp_ticktick_timezone or None
    tz_name: str | None = explicit_tz or env_tz
    tz: ZoneInfo | None = _validate_timezone(tz_name) if tz_name else None

    has_time_of_day = any(
        _has_time_of_day(params, f) for f in ("startDate", "dueDate")
    )
    has_date_only = any(
        _has_date_only(params, f) for f in ("startDate", "dueDate")
    )

    # 3. Normalize dates. _normalize_date raises if a time-of-day was passed
    #    but tz is still None, so by the time we leave this loop a resolved
    #    zone has been used iff has_time_of_day is true.
    for field in ("startDate", "dueDate"):
        if params.get(field) is not None:
            params[field] = _normalize_date(params[field], field, tz)

    # 4. Infer isAllDay from date shape when not passed explicitly.
    isAllDay_explicit = "isAllDay" in params
    if has_date_only and not isAllDay_explicit:
        params["isAllDay"] = True

    # 5. Fail-fast on UpdateTask: changing reminders/startDate/dueDate without
    #    a fresh isAllDay drops it silently on the wire. Trigger validation
    #    requires a known mode anyway, so this check belongs here. The
    #    `"isAllDay" not in params` term also excludes step 4's date-only
    #    inference - the only path that could have resolved a mode implicitly.
    if (
        is_update
        and not isAllDay_explicit
        and "isAllDay" not in params
        and any(f in params for f in _REMINDER_TRIGGERING_FIELDS)
    ):
        raise ValueError(
            "isAllDay must be passed explicitly when changing reminders, "
            "startDate, or dueDate on UpdateTask — the API silently drops "
            "it otherwise. Use isAllDay=true for date-only/whole-day tasks "
            "(reminder trigger format: PT9H = 9am offset from midnight), "
            "or isAllDay=false for timed tasks (trigger format: -PT5M = "
            "5min before event)."
        )

    # 6. CreateTask with reminders: if isAllDay can be inferred (date-only OR
    #    time-of-day on startDate/dueDate), set it explicitly so the API
    #    interprets reminder triggers against the same mode we validated under.
    if "reminders" in params and not isAllDay_explicit:
        if has_date_only:
            params["isAllDay"] = True
        elif has_time_of_day:
            params["isAllDay"] = False
        elif not is_update:
            raise ValueError(
                "reminders requires isAllDay to be determinable on CreateTask "
                "— either pass isAllDay explicitly, or use a date-only "
                "startDate/dueDate (which implies isAllDay=true), or pass a "
                "startDate/dueDate with a time-of-day (which implies "
                "isAllDay=false). Reminder trigger format depends on the mode: "
                "PT9H (positive, 9am from midnight) for all-day, -PT5M "
                "(negative, 5min before event) for timed."
            )

    # 7. Validate priorities, coerce isAllDay, validate reminders.
    if params.get("priority") is not None:
        params["priority"] = _validate_priority(params["priority"])
    if "isAllDay" in params:
        params["isAllDay"] = _coerce_bool(params["isAllDay"])
    if "reminders" in params and "isAllDay" in params:
        _validate_reminders(params["reminders"], params["isAllDay"])

    # 8. CreateTask requires a title. UpdateTask requires projectId + taskId
    #    (the latter from tools.py — UpdateTask's signature already enforces
    #    them as required positional args; here we just guard CreateTask).
    if not is_update and not params.get("title"):
        raise ValueError(
            "Required: 'title'. "
            "Call operation='schema', params={'op': 'CreateTask'} for the full spec."
        )

    # 9. Build the wire payload — _UNSET is gone, None is still dropped,
    #    unknown fields silently ignored (forward-compat with new API fields).
    task: dict[str, Any] = {}
    for key in _TASK_API_FIELDS:
        if params.get(key) is not None:
            task[key] = params[key]

    # 10. Compute tz_meta. Emit whenever a zone was resolved (either time-of-day
    #     was normalized, or an explicit timeZone param came through). When
    #     no zone touched any field at all, return None.
    tz_meta: TzMeta | None
    if tz is not None and (has_time_of_day or explicit_tz):
        source = "param" if explicit_tz else "env:MCP_TICKTICK_TIMEZONE"
        tz_meta = TzMeta(used=str(tz), source=source)
    else:
        tz_meta = None

    return task, tz_meta


def _prepare_project(
    params: dict[str, Any],
    is_update: bool = False,
) -> dict[str, Any]:
    """Build a validated project dict for the API."""
    params = {k: v for k, v in params.items() if v is not _UNSET}
    if params.get("viewMode") is not None:
        _validate_enum(params["viewMode"], "viewMode", {"list", "kanban", "timeline"})
    if params.get("kind") is not None:
        _validate_enum(params["kind"], "kind", {"TASK", "NOTE"})
    if not is_update and not params.get("name"):
        raise ValueError(
            "Required: 'name'. "
            "Call operation='schema', params={'op': 'CreateProject'} for the full spec."
        )
    proj: dict[str, Any] = {}
    for key in _PROJECT_API_FIELDS:
        if params.get(key) is not None:
            proj[key] = params[key]
    return proj


def _verify_response(sent: dict[str, Any], received: Any) -> None:
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
