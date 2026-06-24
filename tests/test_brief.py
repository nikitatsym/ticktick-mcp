"""Tests for brief extraction, injection, validation, and slim task logic."""

import pytest

from ticktick_mcp.prepare import _extract_brief, _inject_brief, _slim_task, _validate_brief
from ticktick_mcp.types import TaskDict


# ── _extract_brief ────────────────────────────────────────────────────────────


def test_extract_brief_from_content() -> None:
    task: TaskDict = {"content": "stuff <brief>Buy milk</brief> more"}
    assert _extract_brief(task) == "Buy milk"


def test_extract_brief_from_desc() -> None:
    task: TaskDict = {"desc": "<brief>From desc</brief>"}
    assert _extract_brief(task) == "From desc"


def test_extract_brief_content_takes_priority() -> None:
    task: TaskDict = {"content": "<brief>From content</brief>", "desc": "<brief>From desc</brief>"}
    assert _extract_brief(task) == "From content"


def test_extract_brief_no_tag() -> None:
    task: TaskDict = {"content": "no tag here"}
    assert _extract_brief(task) is None


def test_extract_brief_empty() -> None:
    assert _extract_brief({}) is None


def test_extract_brief_strips_whitespace() -> None:
    task: TaskDict = {"content": "<brief>  padded  </brief>"}
    assert _extract_brief(task) == "padded"


def test_extract_brief_multiline() -> None:
    task: TaskDict = {"content": "<brief>\nline1\nline2\n</brief>"}
    assert _extract_brief(task) == "line1\nline2"


# ── _inject_brief ─────────────────────────────────────────────────────────────


def test_inject_brief_no_content() -> None:
    assert _inject_brief("Buy milk", None) == "<brief>Buy milk</brief>"


def test_inject_brief_empty_content() -> None:
    assert _inject_brief("Buy milk", "") == "<brief>Buy milk</brief>"


def test_inject_brief_prepends_to_content() -> None:
    result = _inject_brief("Buy milk", "existing notes")
    assert result == "<brief>Buy milk</brief>\nexisting notes"


def test_inject_brief_replaces_existing() -> None:
    result = _inject_brief("New", "before <brief>Old</brief> after")
    assert result == "before <brief>New</brief> after"


def test_inject_brief_replaces_all_occurrences() -> None:
    result = _inject_brief("New", "<brief>A</brief> mid <brief>B</brief>")
    assert result == "<brief>New</brief> mid <brief>New</brief>"


# ── _slim_task ────────────────────────────────────────────────────────────────

FULL_TASK: TaskDict = {
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


def test_slim_keeps_only_essential_fields() -> None:
    result = _slim_task(FULL_TASK)
    assert set(result.keys()) == {
        "id", "projectId", "title", "status", "priority",
        "dueDate", "tags", "parentId", "childIds",
    }
    assert result["id"] == "abc123"
    assert result["title"] == "Buy groceries"


def test_slim_no_desc_or_content() -> None:
    result = _slim_task(FULL_TASK)
    assert "content" not in result
    assert "desc" not in result
    assert "brief" not in result


def test_slim_strips_verbose_fields() -> None:
    result = _slim_task(FULL_TASK)
    for field in ("items", "reminders", "repeatFlag", "sortOrder", "etag",
                  "modifiedTime", "timeZone", "isAllDay", "completedTime",
                  "kind", "columnId", "startDate"):
        assert field not in result


def test_slim_missing_optional_fields() -> None:
    """Slim handles tasks that lack optional fields like tags, parentId."""
    minimal: TaskDict = {"id": "x", "title": "Minimal", "status": 0}
    result = _slim_task(minimal)
    assert result == {"id": "x", "title": "Minimal", "status": 0}


# ── _validate_brief ──────────────────────────────────────────────────────────


class TestValidateBriefContentPath:
    """Brief validation via the content path (no `brief` parameter)."""

    def test_valid_brief_in_content(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        _validate_brief("<brief>Short summary</brief>\nFull body.")

    def test_missing_brief_tag_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief("Content without brief tag")

    def test_none_content_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief(None)

    def test_empty_content_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief("")

    def test_too_long_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        with pytest.raises(ValueError, match="too long"):
            _validate_brief(f"<brief>{'x' * 201}</brief>")

    def test_at_max_length_ok(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        _validate_brief(f"<brief>{'x' * 200}</brief>")

    def test_disabled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "0")
        _validate_brief("no brief, no problem")
        _validate_brief(None)

    def test_custom_max_length(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "50")
        _validate_brief(f"<brief>{'x' * 50}</brief>")
        with pytest.raises(ValueError, match="too long"):
            _validate_brief(f"<brief>{'x' * 51}</brief>")


class TestValidateBriefParamPath:
    """Brief validation via the `brief` parameter path."""

    def test_valid_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        _validate_brief(None, brief_param="A short summary")

    def test_empty_param_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "200")
        with pytest.raises(ValueError, match="brief parameter must be non-empty"):
            _validate_brief(None, brief_param="")

    def test_param_too_long_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "50")
        with pytest.raises(ValueError, match="brief too long"):
            _validate_brief(None, brief_param="x" * 51)

    def test_disabled_skips_param_check(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_BRIEF_MAX", "0")
        _validate_brief(None, brief_param="")  # empty allowed when off
