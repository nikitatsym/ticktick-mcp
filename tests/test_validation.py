"""Tests for input validation and response verification."""

import pytest

from ticktick_mcp.server import (
    _normalize_date,
    _prepare_project,
    _prepare_task,
    _require,
    _validate_enum,
    _validate_priority,
    _verify_response,
)


# ── _normalize_date ──────────────────────────────────────────────────────────


class TestNormalizeDate:
    def test_date_only(self):
        assert _normalize_date("2026-03-20", "dueDate") == "2026-03-20T00:00:00.000+0000"

    def test_datetime_with_tz_offset(self):
        val = "2026-03-20T10:00:00.000+0300"
        assert _normalize_date(val, "dueDate") == val

    def test_datetime_with_tz_no_colon(self):
        val = "2026-03-20T10:00:00+0000"
        assert _normalize_date(val, "dueDate") == val

    def test_datetime_with_tz_colon(self):
        val = "2026-03-20T10:00:00+03:00"
        assert _normalize_date(val, "dueDate") == val

    def test_datetime_with_z(self):
        val = "2026-03-20T10:00:00Z"
        assert _normalize_date(val, "dueDate") == val

    def test_datetime_with_millis_and_tz(self):
        val = "2026-03-20T10:00:00.000+0000"
        assert _normalize_date(val, "dueDate") == val

    def test_datetime_no_tz_raises(self):
        with pytest.raises(ValueError, match="without timezone"):
            _normalize_date("2026-03-20T10:00:00", "dueDate")

    def test_datetime_no_tz_with_millis_raises(self):
        with pytest.raises(ValueError, match="without timezone"):
            _normalize_date("2026-03-20T10:00:00.000", "startDate")

    def test_garbage_raises(self):
        with pytest.raises(ValueError, match="invalid format"):
            _normalize_date("next tuesday", "dueDate")

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="invalid format"):
            _normalize_date("", "dueDate")

    def test_field_name_in_error(self):
        with pytest.raises(ValueError, match="startDate"):
            _normalize_date("bad", "startDate")


# ── _validate_priority ───────────────────────────────────────────────────────


class TestValidatePriority:
    @pytest.mark.parametrize("val", [0, 1, 3, 5])
    def test_valid_int(self, val):
        assert _validate_priority(val) == val

    @pytest.mark.parametrize("val", ["0", "1", "3", "5"])
    def test_str_coercion(self, val):
        assert _validate_priority(val) == int(val)

    @pytest.mark.parametrize("val", [2, 4, -1, 6, 10])
    def test_invalid_raises(self, val):
        with pytest.raises(ValueError, match="priority must be"):
            _validate_priority(val)

    def test_str_non_numeric_raises(self):
        with pytest.raises(ValueError, match="priority must be"):
            _validate_priority("high")


# ── _validate_enum ───────────────────────────────────────────────────────────


class TestValidateEnum:
    def test_valid(self):
        assert _validate_enum("kanban", "viewMode", {"list", "kanban", "timeline"}) == "kanban"

    def test_all_valid_values(self):
        for v in ("list", "kanban", "timeline"):
            assert _validate_enum(v, "viewMode", {"list", "kanban", "timeline"}) == v

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="viewMode"):
            _validate_enum("grid", "viewMode", {"list", "kanban", "timeline"})

    def test_kind_valid(self):
        assert _validate_enum("TASK", "kind", {"TASK", "NOTE"}) == "TASK"
        assert _validate_enum("NOTE", "kind", {"TASK", "NOTE"}) == "NOTE"

    def test_kind_invalid(self):
        with pytest.raises(ValueError, match="kind"):
            _validate_enum("HABIT", "kind", {"TASK", "NOTE"})


# ── _require ─────────────────────────────────────────────────────────────────


class TestRequire:
    def test_all_present(self):
        _require({"title": "T", "projectId": "p"}, "title")

    def test_multiple_present(self):
        _require({"projectId": "p", "taskId": "t"}, "projectId", "taskId")

    def test_missing_raises(self):
        with pytest.raises(ValueError, match="'title'"):
            _require({"projectId": "p"}, "title")

    def test_none_value_raises(self):
        with pytest.raises(ValueError, match="'title'"):
            _require({"title": None}, "title")

    def test_error_shows_got(self):
        with pytest.raises(ValueError, match="projectId"):
            _require({"projectId": "p"}, "title")


# ── _verify_response ────────────────────────────────────────────────────────


class TestVerifyResponse:
    def test_all_fields_present(self):
        _verify_response(
            {"title": "T", "priority": 3},
            {"title": "T", "priority": 3, "id": "x"},
        )

    def test_field_dropped_raises(self):
        with pytest.raises(ValueError, match="dueDate"):
            _verify_response(
                {"title": "T", "dueDate": "2026-03-20T00:00:00.000+0000"},
                {"title": "T"},
            )

    def test_content_skipped(self):
        _verify_response({"title": "T", "content": "text"}, {"title": "T"})

    def test_desc_skipped(self):
        _verify_response({"title": "T", "desc": "d"}, {"title": "T"})

    def test_non_dict_response_ignored(self):
        _verify_response({"title": "T"}, "some string")

    def test_none_response_ignored(self):
        _verify_response({"title": "T"}, None)

    def test_extra_fields_in_response_ok(self):
        _verify_response({"title": "T"}, {"title": "T", "id": "x", "status": 0})


# ── _prepare_task ────────────────────────────────────────────────────────────


class TestPrepareTask:
    def test_create_basic(self):
        result = _prepare_task({"title": "Buy milk", "brief": "Buy milk"})
        assert result["title"] == "Buy milk"
        assert "<brief>Buy milk</brief>" in result["content"]
        assert "brief" not in result

    def test_create_normalizes_date(self):
        result = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-20"})
        assert result["dueDate"] == "2026-03-20T00:00:00.000+0000"

    def test_create_passes_tz_date(self):
        result = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-20T10:00:00+0300"})
        assert result["dueDate"] == "2026-03-20T10:00:00+0300"

    def test_create_validates_priority(self):
        with pytest.raises(ValueError, match="priority must be"):
            _prepare_task({"title": "T", "brief": "B", "priority": 2})

    def test_create_coerces_priority_str(self):
        result = _prepare_task({"title": "T", "brief": "B", "priority": "3"})
        assert result["priority"] == 3

    def test_create_requires_title(self):
        with pytest.raises(ValueError, match="'title'"):
            _prepare_task({"brief": "B"})

    def test_update_requires_projectId_taskId(self):
        with pytest.raises(ValueError, match="'projectId'"):
            _prepare_task({"title": "T"}, is_update=True)

    def test_update_basic(self):
        result = _prepare_task({"projectId": "p1", "taskId": "t1", "title": "New"}, is_update=True)
        assert result["projectId"] == "p1"
        assert result["title"] == "New"
        assert "taskId" not in result

    def test_skips_none_values(self):
        result = _prepare_task({"title": "T", "brief": "B", "dueDate": None, "priority": None})
        assert "dueDate" not in result
        assert "priority" not in result

    def test_coerces_isAllDay_bool(self):
        result = _prepare_task({"title": "T", "brief": "B", "isAllDay": True})
        assert result["isAllDay"] is True

    def test_coerces_isAllDay_str(self):
        result = _prepare_task({"title": "T", "brief": "B", "isAllDay": "true"})
        assert result["isAllDay"] is True

    def test_coerces_isAllDay_str_false(self):
        result = _prepare_task({"title": "T", "brief": "B", "isAllDay": "false"})
        assert result["isAllDay"] is False

    def test_does_not_mutate_input(self):
        params = {"title": "T", "brief": "B", "dueDate": "2026-03-20"}
        _prepare_task(params)
        assert params["dueDate"] == "2026-03-20"
        assert "brief" in params

    def test_datetime_no_tz_rejected(self):
        with pytest.raises(ValueError, match="without timezone"):
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-20T10:00:00"})

    def test_update_skips_brief_validation_when_no_content(self):
        """Update without content change should not require brief."""
        result = _prepare_task({"projectId": "p1", "taskId": "t1", "title": "New"}, is_update=True)
        assert result["title"] == "New"


# ── _prepare_project ─────────────────────────────────────────────────────────


class TestPrepareProject:
    def test_create_basic(self):
        result = _prepare_project({"name": "Work"})
        assert result == {"name": "Work"}

    def test_create_with_viewMode(self):
        result = _prepare_project({"name": "Work", "viewMode": "kanban"})
        assert result == {"name": "Work", "viewMode": "kanban"}

    def test_create_requires_name(self):
        with pytest.raises(ValueError, match="'name'"):
            _prepare_project({"viewMode": "kanban"})

    def test_invalid_viewMode(self):
        with pytest.raises(ValueError, match="viewMode"):
            _prepare_project({"name": "Work", "viewMode": "grid"})

    def test_invalid_kind(self):
        with pytest.raises(ValueError, match="kind"):
            _prepare_project({"name": "Work", "kind": "INVALID"})

    def test_update_no_require_name(self):
        result = _prepare_project({"color": "#ff0000"}, is_update=True)
        assert result == {"color": "#ff0000"}

    def test_valid_kind(self):
        result = _prepare_project({"name": "Notes", "kind": "NOTE"})
        assert result["kind"] == "NOTE"

    def test_does_not_mutate_input(self):
        params = {"name": "Work", "viewMode": "kanban"}
        _prepare_project(params)
        assert params == {"name": "Work", "viewMode": "kanban"}

    def test_skips_unknown_fields(self):
        result = _prepare_project({"name": "Work", "projectId": "p1"})
        assert "projectId" not in result
