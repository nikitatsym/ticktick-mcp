"""Tests for input validation, normalization, and response verification."""

from zoneinfo import ZoneInfo

import pytest

from ticktick_mcp import server as server_module
from ticktick_mcp import tools as tools_module
from ticktick_mcp.prepare import (
    _normalize_date,
    _prepare_project,
    _prepare_task,
    _validate_enum,
    _validate_priority,
    _validate_timezone,
    _verify_response,
)
from ticktick_mcp.registry import Group

# ── _validate_timezone ───────────────────────────────────────────────────────


class TestValidateTimezone:
    def test_valid(self) -> None:
        tz = _validate_timezone("Europe/Berlin")
        assert tz == ZoneInfo("Europe/Berlin")

    def test_valid_utc(self) -> None:
        _validate_timezone("UTC")

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown timezone"):
            _validate_timezone("Mars/Olympus")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown timezone"):
            _validate_timezone("")


# ── _normalize_date ──────────────────────────────────────────────────────────


class TestNormalizeDate:
    _tz_berlin = ZoneInfo("Europe/Berlin")
    _tz_dubai = ZoneInfo("Asia/Dubai")

    def test_date_only_no_tz(self) -> None:
        assert _normalize_date("2026-03-20", "dueDate", None) == "2026-03-20T00:00:00.000+0000"

    def test_date_only_with_tz(self) -> None:
        assert _normalize_date("2026-03-20", "dueDate", self._tz_berlin) == "2026-03-20T00:00:00.000+0000"

    def test_naive_datetime_with_tz(self) -> None:
        result = _normalize_date("2026-03-15T19:00:00", "dueDate", self._tz_berlin)
        assert result == "2026-03-15T19:00:00.000+0100"

    def test_naive_datetime_dubai(self) -> None:
        result = _normalize_date("2026-03-15T15:00:00", "dueDate", self._tz_dubai)
        assert result == "2026-03-15T15:00:00.000+0400"

    def test_naive_datetime_short_form(self) -> None:
        result = _normalize_date("2026-03-15T19:00", "dueDate", self._tz_berlin)
        assert result == "2026-03-15T19:00:00.000+0100"

    def test_naive_datetime_no_tz_raises(self) -> None:
        with pytest.raises(ValueError, match="no timeZone"):
            _normalize_date("2026-03-20T10:00:00", "dueDate", None)

    def test_manual_offset_rejected(self) -> None:
        with pytest.raises(ValueError, match="manual UTC offsets are not allowed"):
            _normalize_date("2026-03-20T10:00:00+0300", "dueDate", self._tz_berlin)

    def test_manual_offset_z_rejected(self) -> None:
        with pytest.raises(ValueError, match="manual UTC offsets are not allowed"):
            _normalize_date("2026-03-20T10:00:00Z", "dueDate", None)

    def test_dst_transition(self) -> None:
        result = _normalize_date("2026-03-30T10:00:00", "dueDate", self._tz_berlin)
        assert result == "2026-03-30T10:00:00.000+0200"

    def test_garbage_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid format"):
            _normalize_date("next tuesday", "dueDate", None)

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid format"):
            _normalize_date("", "dueDate", None)

    def test_field_name_in_error(self) -> None:
        with pytest.raises(ValueError, match="startDate"):
            _normalize_date("bad", "startDate", None)


# ── _validate_priority ───────────────────────────────────────────────────────


class TestValidatePriority:
    @pytest.mark.parametrize("val", [0, 1, 3, 5])
    def test_valid_int(self, val: int) -> None:
        assert _validate_priority(val) == val

    @pytest.mark.parametrize("val", ["0", "1", "3", "5"])
    def test_str_coercion(self, val: str) -> None:
        assert _validate_priority(val) == int(val)

    @pytest.mark.parametrize("val", [2, 4, -1, 6, 10])
    def test_invalid_raises(self, val: int) -> None:
        with pytest.raises(ValueError, match="priority must be"):
            _validate_priority(val)

    def test_str_non_numeric_raises(self) -> None:
        with pytest.raises(ValueError, match="priority must be"):
            _validate_priority("high")


# ── _validate_enum ───────────────────────────────────────────────────────────


class TestValidateEnum:
    def test_valid(self) -> None:
        assert _validate_enum("kanban", "viewMode", {"list", "kanban", "timeline"}) == "kanban"

    def test_all_valid_values(self) -> None:
        for v in ("list", "kanban", "timeline"):
            assert _validate_enum(v, "viewMode", {"list", "kanban", "timeline"}) == v

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="viewMode"):
            _validate_enum("grid", "viewMode", {"list", "kanban", "timeline"})

    def test_kind_valid(self) -> None:
        assert _validate_enum("TASK", "kind", {"TASK", "NOTE"}) == "TASK"
        assert _validate_enum("NOTE", "kind", {"TASK", "NOTE"}) == "NOTE"

    def test_kind_invalid(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            _validate_enum("HABIT", "kind", {"TASK", "NOTE"})


# ── _verify_response ────────────────────────────────────────────────────────


class TestVerifyResponse:
    def test_all_fields_present(self) -> None:
        _verify_response(
            {"title": "T", "priority": 3},
            {"title": "T", "priority": 3, "id": "x"},
        )

    def test_field_dropped_raises(self) -> None:
        with pytest.raises(ValueError, match="dueDate"):
            _verify_response(
                {"title": "T", "dueDate": "2026-03-20T00:00:00.000+0000"},
                {"title": "T"},
            )

    def test_content_skipped(self) -> None:
        _verify_response({"title": "T", "content": "text"}, {"title": "T"})

    def test_desc_skipped(self) -> None:
        _verify_response({"title": "T", "desc": "d"}, {"title": "T"})

    def test_non_dict_response_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot verify"):
            _verify_response({"title": "T"}, "some string")

    def test_none_response_raises(self) -> None:
        with pytest.raises(ValueError, match="cannot verify"):
            _verify_response({"title": "T"}, None)

    def test_extra_fields_in_response_ok(self) -> None:
        _verify_response({"title": "T"}, {"title": "T", "id": "x", "status": 0})


# ── _prepare_task ────────────────────────────────────────────────────────────


class TestPrepareTask:
    def test_create_basic(self) -> None:
        task = _prepare_task({"title": "Buy milk", "brief": "Buy milk"})
        assert task["title"] == "Buy milk"
        assert "<brief>Buy milk</brief>" in task["content"]
        assert "brief" not in task

    def test_create_normalizes_date_only(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-20"})
        assert task["dueDate"] == "2026-03-20T00:00:00.000+0000"

    def test_create_normalizes_datetime_with_tz(self) -> None:
        task = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-03-20T10:00:00", "timeZone": "Asia/Dubai",
        })
        assert task["dueDate"] == "2026-03-20T10:00:00.000+0400"
        assert task["timeZone"] == "Asia/Dubai"

    def test_create_rejects_manual_offset(self) -> None:
        with pytest.raises(ValueError, match="manual UTC offsets"):
            _prepare_task({
                "title": "T", "brief": "B",
                "dueDate": "2026-03-20T10:00:00+0300",
            })

    def test_create_validates_priority(self) -> None:
        with pytest.raises(ValueError, match="priority must be"):
            _prepare_task({"title": "T", "brief": "B", "priority": 2})

    def test_create_coerces_priority_str(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "priority": "3"})
        assert task["priority"] == 3

    def test_create_requires_title(self) -> None:
        with pytest.raises(ValueError, match="title"):
            _prepare_task({"brief": "B"})

    def test_update_basic(self) -> None:
        task = _prepare_task(
            {"projectId": "p1", "title": "New"},
            is_update=True,
        )
        assert task["projectId"] == "p1"
        assert task["title"] == "New"
        assert "taskId" not in task

    def test_skips_none_values(self) -> None:
        task = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": None, "priority": None,
        })
        assert "dueDate" not in task
        assert "priority" not in task

    def test_coerces_isAllDay_bool(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "isAllDay": True})
        assert task["isAllDay"] is True

    def test_coerces_isAllDay_str(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "isAllDay": "true"})
        assert task["isAllDay"] is True

    def test_coerces_isAllDay_str_false(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "isAllDay": "false"})
        assert task["isAllDay"] is False

    def test_date_only_auto_isAllDay(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-20"})
        assert task["isAllDay"] is True

    def test_date_only_explicit_isAllDay_false(self) -> None:
        task = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-03-20", "isAllDay": False,
        })
        assert task["isAllDay"] is False

    def test_datetime_no_auto_isAllDay(self) -> None:
        task = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-03-20T10:00:00", "timeZone": "Asia/Dubai",
        })
        assert "isAllDay" not in task

    def test_startDate_date_only_auto_isAllDay(self) -> None:
        task = _prepare_task({"title": "T", "brief": "B", "startDate": "2026-03-20"})
        assert task["isAllDay"] is True

    def test_does_not_mutate_input(self) -> None:
        params = {"title": "T", "brief": "B", "dueDate": "2026-03-20"}
        _prepare_task(params)
        assert params["dueDate"] == "2026-03-20"
        assert "brief" in params

    def test_datetime_no_tz_rejected(self) -> None:
        with pytest.raises(ValueError, match="no timeZone"):
            _prepare_task({
                "title": "T", "brief": "B",
                "dueDate": "2026-03-20T10:00:00",
            })

    def test_update_no_brief_no_content_skips_validation(self) -> None:
        """Update with neither brief nor content should not trigger brief validation."""
        task = _prepare_task(
            {"projectId": "p1", "title": "New"},
            is_update=True,
        )
        assert task["title"] == "New"


# ── _prepare_project ─────────────────────────────────────────────────────────


class TestPrepareProject:
    def test_create_basic(self) -> None:
        result = _prepare_project({"name": "Work"})
        assert result == {"name": "Work"}

    def test_create_with_viewMode(self) -> None:
        result = _prepare_project({"name": "Work", "viewMode": "kanban"})
        assert result == {"name": "Work", "viewMode": "kanban"}

    def test_create_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            _prepare_project({"viewMode": "kanban"})

    def test_invalid_viewMode(self) -> None:
        with pytest.raises(ValueError, match="viewMode"):
            _prepare_project({"name": "Work", "viewMode": "grid"})

    def test_invalid_kind(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            _prepare_project({"name": "Work", "kind": "INVALID"})

    def test_update_no_require_name(self) -> None:
        result = _prepare_project({"color": "#ff0000"}, is_update=True)
        assert result == {"color": "#ff0000"}

    def test_valid_kind(self) -> None:
        result = _prepare_project({"name": "Notes", "kind": "NOTE"})
        assert result["kind"] == "NOTE"

    def test_does_not_mutate_input(self) -> None:
        params = {"name": "Work", "viewMode": "kanban"}
        _prepare_project(params)
        assert params == {"name": "Work", "viewMode": "kanban"}

    def test_skips_unknown_fields(self) -> None:
        result = _prepare_project({"name": "Work", "projectId": "p1"})
        assert "projectId" not in result


# ── Registration ─────────────────────────────────────────────────────────────


class TestRegistration:
    def test_import_succeeds(self) -> None:
        from ticktick_mcp.server import mcp

    def test_all_decorated_functions_have_docstrings(self) -> None:
        import inspect

        from ticktick_mcp import tools as tools_module

        for name, fn in inspect.getmembers(tools_module, inspect.isfunction):
            if hasattr(fn, "_mcp_group"):
                assert fn.__doc__, f"{name} has @_op but no docstring"

    def test_all_groups_have_docs(self) -> None:
        import inspect

        from ticktick_mcp import tools as tools_module
        from ticktick_mcp.registry import ROOT

        groups = {
            fn._mcp_group
            for _, fn in inspect.getmembers(tools_module, inspect.isfunction)
            if hasattr(fn, "_mcp_group") and fn._mcp_group is not ROOT
        }
        for group in groups:
            assert group.doc, f"group {group.name!r} has no doc"


# ── Group doc templating ─────────────────────────────────────────────────────


class TestGroupDocTemplate:
    def test_group_docs_resolve_operation_placeholders(self) -> None:
        groups = [
            obj
            for obj in vars(tools_module).values()
            if isinstance(obj, Group) and obj.name in server_module._group_ops
        ]
        assert len(groups) == len(server_module._group_ops)
        for group in groups:
            rendered = server_module._render_group_doc(
                group.name, group.doc, server_module._group_ops[group.name]
            )
            assert "$" not in rendered, f"{group.name} doc left a placeholder unrendered"

    def test_unknown_placeholder_raises(self) -> None:
        with pytest.raises(RuntimeError, match="NoSuchOp"):
            server_module._render_group_doc(
                "ticktick_read",
                "ticktick_read(operation='$NoSuchOp')",
                server_module._group_ops["ticktick_read"],
            )

    def test_hardcoded_operation_raises(self) -> None:
        with pytest.raises(RuntimeError, match="hardcodes"):
            server_module._render_group_doc(
                "ticktick_read",
                "ticktick_read(operation='GetToday')",
                server_module._group_ops["ticktick_read"],
            )

        with pytest.raises(RuntimeError, match="hardcodes"):
            server_module._render_group_doc(
                "ticktick_read",
                "ticktick_read(operation = 'GetToday')",
                server_module._group_ops["ticktick_read"],
            )

    def test_meta_operations_resolve_and_generic_form_passes_through(self) -> None:
        rendered = server_module._render_group_doc(
            "ticktick_read",
            "operation='$help' operation='$schema' operation='<OpName>'",
            {},
        )
        assert rendered == "operation='help' operation='schema' operation='<OpName>'"

    def test_registered_op_name_resolves(self) -> None:
        rendered = server_module._render_group_doc(
            "ticktick_read",
            "ticktick_read(operation='$GetToday')",
            server_module._group_ops["ticktick_read"],
        )
        assert rendered == "ticktick_read(operation='GetToday')"
