"""Tests for brief injection, validation, and slim task logic."""

from unittest.mock import MagicMock

import pytest

from ticktick_mcp import tools
from ticktick_mcp.config import Settings
from ticktick_mcp.prepare import (
    _inject_brief,
    _validate_brief,
    slim_task,
)
from ticktick_mcp.types import TaskDict


def test_brief_limit_comes_from_the_bound_instance() -> None:
    """Under mcps-host each instance binds its own client; its limit must apply."""
    strict, lax = MagicMock(), MagicMock()
    strict.settings = Settings(mcp_ticktick_brief_max=5)
    lax.settings = Settings(mcp_ticktick_brief_max=100)
    lax.create_task.side_effect = lambda task: {**task, "id": "n1"}

    token = tools.client_var.set(strict)
    try:
        with pytest.raises(ValueError, match="brief too long"):
            tools.create_task(title="T", brief="ten chars!")
    finally:
        tools.client_var.reset(token)
    strict.create_task.assert_not_called()

    token = tools.client_var.set(lax)
    try:
        assert tools.create_task(title="T", brief="ten chars!")["id"] == "n1"
    finally:
        tools.client_var.reset(token)


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


# ── slim_task ────────────────────────────────────────────────────────────────

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
    result = slim_task(FULL_TASK)
    assert set(result.keys()) == {
        "id", "projectId", "title", "status", "priority",
        "dueDate", "tags", "parentId", "childIds",
    }
    assert result["id"] == "abc123"
    assert result["title"] == "Buy groceries"


def test_slim_no_desc_or_content() -> None:
    result = slim_task(FULL_TASK)
    assert "content" not in result
    assert "desc" not in result
    assert "brief" not in result


def test_slim_strips_verbose_fields() -> None:
    result = slim_task(FULL_TASK)
    for field in ("items", "reminders", "repeatFlag", "sortOrder", "etag",
                  "modifiedTime", "timeZone", "isAllDay", "completedTime",
                  "kind", "columnId", "startDate"):
        assert field not in result


def test_slim_missing_optional_fields() -> None:
    """Slim handles tasks that lack optional fields like tags, parentId."""
    minimal: TaskDict = {"id": "x", "title": "Minimal", "status": 0}
    result = slim_task(minimal)
    assert result == {"id": "x", "title": "Minimal", "status": 0}


# ── _validate_brief ──────────────────────────────────────────────────────────


class TestValidateBriefContentPath:
    """Brief validation via the content path (no `brief` parameter)."""

    def test_valid_brief_in_content(self) -> None:
        _validate_brief("<brief>Short summary</brief>\nFull body.", brief_max=200)

    def test_missing_brief_tag_raises(self) -> None:
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief("Content without brief tag", brief_max=200)

    def test_none_content_raises(self) -> None:
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief(None, brief_max=200)

    def test_empty_content_raises(self) -> None:
        with pytest.raises(ValueError, match="Pass the 'brief' parameter"):
            _validate_brief("", brief_max=200)

    def test_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            _validate_brief(f"<brief>{'x' * 201}</brief>", brief_max=200)

    def test_at_max_length_ok(self) -> None:
        _validate_brief(f"<brief>{'x' * 200}</brief>", brief_max=200)

    def test_disabled(self) -> None:
        _validate_brief("no brief, no problem", brief_max=0)
        _validate_brief(None, brief_max=0)

    def test_custom_max_length(self) -> None:
        _validate_brief(f"<brief>{'x' * 50}</brief>", brief_max=50)
        with pytest.raises(ValueError, match="too long"):
            _validate_brief(f"<brief>{'x' * 51}</brief>", brief_max=50)


class TestValidateBriefParamPath:
    """Brief validation via the `brief` parameter path."""

    def test_valid_param(self) -> None:
        _validate_brief(None, brief_param="A short summary", brief_max=200)

    def test_empty_param_raises(self) -> None:
        with pytest.raises(ValueError, match="brief parameter must be non-empty"):
            _validate_brief(None, brief_param="", brief_max=200)

    def test_param_too_long_raises(self) -> None:
        with pytest.raises(ValueError, match="brief too long"):
            _validate_brief(None, brief_param="x" * 51, brief_max=50)

    def test_disabled_skips_param_check(self) -> None:
        _validate_brief(None, brief_param="", brief_max=0)  # empty allowed when off
