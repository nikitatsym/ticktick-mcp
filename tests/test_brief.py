"""Tests for brief extraction, injection, and task processing logic."""

from ticktick_mcp.server import _extract_brief, _inject_brief, _process_tasks, _slim_task


# ── _extract_brief ────────────────────────────────────────────────────────────


def test_extract_brief_from_content():
    task = {"content": "stuff <brief>Buy milk</brief> more"}
    assert _extract_brief(task) == "Buy milk"


def test_extract_brief_from_desc():
    task = {"desc": "<brief>From desc</brief>"}
    assert _extract_brief(task) == "From desc"


def test_extract_brief_content_takes_priority():
    task = {"content": "<brief>From content</brief>", "desc": "<brief>From desc</brief>"}
    assert _extract_brief(task) == "From content"


def test_extract_brief_no_tag():
    assert _extract_brief({"content": "no tag here"}) is None


def test_extract_brief_empty():
    assert _extract_brief({}) is None


def test_extract_brief_strips_whitespace():
    task = {"content": "<brief>  padded  </brief>"}
    assert _extract_brief(task) == "padded"


def test_extract_brief_multiline():
    task = {"content": "<brief>\nline1\nline2\n</brief>"}
    assert _extract_brief(task) == "line1\nline2"


# ── _inject_brief ─────────────────────────────────────────────────────────────


def test_inject_brief_no_content():
    assert _inject_brief("Buy milk", None) == "<brief>Buy milk</brief>"


def test_inject_brief_empty_content():
    assert _inject_brief("Buy milk", "") == "<brief>Buy milk</brief>"


def test_inject_brief_prepends_to_content():
    result = _inject_brief("Buy milk", "existing notes")
    assert result == "<brief>Buy milk</brief>\nexisting notes"


def test_inject_brief_replaces_existing():
    result = _inject_brief("New", "before <brief>Old</brief> after")
    assert result == "before <brief>New</brief> after"


def test_inject_brief_replaces_all_occurrences():
    result = _inject_brief("New", "<brief>A</brief> mid <brief>B</brief>")
    assert result == "<brief>New</brief> mid <brief>New</brief>"


# ── _process_tasks ─────────────────────────────────────────────────────────────

SAMPLE_TASKS = [
    {"id": "1", "title": "Has brief", "content": "Full <brief>Buy milk</brief> rest", "desc": "short"},
    {"id": "2", "title": "No brief", "content": "Just text", "desc": "also text"},
    {"id": "3", "title": "No content"},
]


def test_process_full_descriptions():
    result = _process_tasks(SAMPLE_TASKS, desc=True, descCompact=False)
    assert result is SAMPLE_TASKS  # no copy needed
    assert "content" in result[0]
    assert "desc" in result[0]


def test_process_no_desc():
    result = _process_tasks(SAMPLE_TASKS, desc=False, descCompact=False)
    for task in result:
        assert "content" not in task
        assert "desc" not in task
        assert "brief" not in task
    assert result[0]["title"] == "Has brief"


def test_process_compact_with_brief():
    result = _process_tasks(SAMPLE_TASKS, desc=True, descCompact=True)
    assert result[0]["brief"] == "Buy milk"
    assert "content" not in result[0]
    assert "desc" not in result[0]


def test_process_compact_without_brief():
    result = _process_tasks(SAMPLE_TASKS, desc=True, descCompact=True)
    assert "brief" not in result[1]  # no tag -> no brief field
    assert "content" not in result[1]
    assert "desc" not in result[1]


def test_process_compact_no_content_task():
    result = _process_tasks(SAMPLE_TASKS, desc=True, descCompact=True)
    assert "brief" not in result[2]
    assert "content" not in result[2]


def test_process_compact_default_also_extracts_brief():
    """desc=False + descCompact=True (default) should still extract brief."""
    result = _process_tasks(SAMPLE_TASKS, desc=False, descCompact=True)
    assert result[0]["brief"] == "Buy milk"
    assert "content" not in result[0]


def test_process_does_not_mutate_original():
    tasks = [{"id": "1", "title": "T", "content": "text", "desc": "d"}]
    _process_tasks(tasks, desc=False, descCompact=False)
    assert "content" in tasks[0]  # original untouched


# ── _slim_task ────────────────────────────────────────────────────────────────

FULL_TASK = {
    "id": "abc123",
    "projectId": "proj1",
    "title": "Buy groceries",
    "status": 0,
    "priority": 3,
    "dueDate": "2026-03-06T00:00:00+0000",
    "tags": ["errands"],
    "parentId": "",
    "childIds": [],
    "content": "Full notes <brief>Weekly shop</brief> more text",
    "desc": "some desc",
    "items": [{"title": "Milk", "status": 0}],
    "reminders": ["TRIGGER:-PT15M"],
    "repeatFlag": "RRULE:FREQ=WEEKLY",
    "sortOrder": -1234567890,
    "etag": "abcdef",
    "modifiedTime": "2026-03-05T10:00:00+0000",
    "timeZone": "America/New_York",
    "isAllDay": True,
    "completedTime": "",
    "kind": "TEXT",
    "columnId": "col1",
    "startDate": "2026-03-05T00:00:00+0000",
}


def test_slim_keeps_only_essential_fields():
    result = _slim_task(FULL_TASK, desc=False, descCompact=False)
    assert set(result.keys()) == {"id", "projectId", "title", "status", "priority", "dueDate", "tags", "parentId", "childIds"}
    assert result["id"] == "abc123"
    assert result["title"] == "Buy groceries"


def test_slim_no_desc():
    result = _slim_task(FULL_TASK, desc=False, descCompact=False)
    assert "content" not in result
    assert "desc" not in result
    assert "brief" not in result


def test_slim_with_desc_compact():
    result = _slim_task(FULL_TASK, desc=True, descCompact=True)
    assert result["brief"] == "Weekly shop"
    assert "content" not in result
    assert "desc" not in result


def test_slim_with_desc_full():
    result = _slim_task(FULL_TASK, desc=True, descCompact=False)
    assert result["content"] == FULL_TASK["content"]
    assert result["desc"] == FULL_TASK["desc"]
    assert "brief" not in result


def test_slim_strips_verbose_fields():
    result = _slim_task(FULL_TASK, desc=False, descCompact=False)
    for field in ("items", "reminders", "repeatFlag", "sortOrder", "etag",
                  "modifiedTime", "timeZone", "isAllDay", "completedTime",
                  "kind", "columnId", "startDate"):
        assert field not in result


def test_slim_no_brief_tag():
    task = {**FULL_TASK, "content": "no brief tag here"}
    result = _slim_task(task, desc=True, descCompact=True)
    assert "brief" not in result


def test_slim_missing_optional_fields():
    """Slim handles tasks that lack optional fields like tags, parentId."""
    minimal = {"id": "x", "title": "Minimal", "status": 0}
    result = _slim_task(minimal, desc=False, descCompact=False)
    assert result == {"id": "x", "title": "Minimal", "status": 0}
