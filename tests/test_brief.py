"""Tests for brief extraction, injection, validation, and slim task logic."""

import importlib
import pytest

from ticktick_mcp.prepare import _extract_brief, _inject_brief, _slim_task


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
    result = _slim_task(FULL_TASK)
    assert set(result.keys()) == {"id", "projectId", "title", "status", "priority", "dueDate", "tags", "parentId", "childIds"}
    assert result["id"] == "abc123"
    assert result["title"] == "Buy groceries"


def test_slim_no_desc_or_content():
    result = _slim_task(FULL_TASK)
    assert "content" not in result
    assert "desc" not in result
    assert "brief" not in result


def test_slim_strips_verbose_fields():
    result = _slim_task(FULL_TASK)
    for field in ("items", "reminders", "repeatFlag", "sortOrder", "etag",
                  "modifiedTime", "timeZone", "isAllDay", "completedTime",
                  "kind", "columnId", "startDate"):
        assert field not in result


def test_slim_missing_optional_fields():
    """Slim handles tasks that lack optional fields like tags, parentId."""
    minimal = {"id": "x", "title": "Minimal", "status": 0}
    result = _slim_task(minimal)
    assert result == {"id": "x", "title": "Minimal", "status": 0}


# ── _validate_brief ──────────────────────────────────────────────────────────


def _reload_prepare(monkeypatch, **env):
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    import ticktick_mcp.prepare as mod
    importlib.reload(mod)
    return mod


@pytest.fixture()
def prep_on(monkeypatch):
    return _reload_prepare(monkeypatch, MCP_TICKTICK_BRIEF_MAX="200")


class TestValidateBrief:
    def test_valid_brief(self, prep_on):
        prep_on._validate_brief("<brief>Short summary</brief>\nFull body.")

    def test_missing_brief_raises(self, prep_on):
        with pytest.raises(ValueError, match="must contain"):
            prep_on._validate_brief("Content without brief tag")

    def test_none_raises(self, prep_on):
        with pytest.raises(ValueError, match="must contain"):
            prep_on._validate_brief(None)

    def test_empty_raises(self, prep_on):
        with pytest.raises(ValueError, match="must contain"):
            prep_on._validate_brief("")

    def test_too_long(self, prep_on):
        with pytest.raises(ValueError, match="too long"):
            prep_on._validate_brief(f"<brief>{'x' * 201}</brief>")

    def test_at_max_length(self, prep_on):
        prep_on._validate_brief(f"<brief>{'x' * 200}</brief>")

    def test_disabled(self, monkeypatch):
        mod = _reload_prepare(monkeypatch, MCP_TICKTICK_BRIEF_MAX="0")
        mod._validate_brief("no brief, no problem")
        mod._validate_brief(None)

    def test_custom_max_length(self, monkeypatch):
        mod = _reload_prepare(monkeypatch, MCP_TICKTICK_BRIEF_MAX="50")
        mod._validate_brief(f"<brief>{'x' * 50}</brief>")
        with pytest.raises(ValueError, match="too long"):
            mod._validate_brief(f"<brief>{'x' * 51}</brief>")
