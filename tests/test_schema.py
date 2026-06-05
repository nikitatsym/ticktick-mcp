"""JSON Schema (operation='schema'): per-op model_json_schema() shape."""

import pytest

from ticktick_mcp.server import _build_schema


class TestCreateTaskSchema:
    def setup_method(self):
        self.schema = _build_schema("ticktick_write", "CreateTask")

    def test_required_is_just_title(self):
        """Brief is a runtime cross-field rule, NOT a schema-required field."""
        assert self.schema["required"] == ["title"]

    def test_additional_properties_forbidden(self):
        assert self.schema["additionalProperties"] is False

    def test_brief_field_present_with_description(self):
        brief = self.schema["properties"]["brief"]
        assert brief.get("description")
        assert "brief" in brief["description"].lower()

    def test_brief_field_optional_in_schema(self):
        assert "brief" not in self.schema["required"]

    def test_timezone_field_documents_fallback(self):
        tz = self.schema["properties"]["timeZone"]
        assert "MCP_TICKTICK_TIMEZONE" in tz["description"]

    def test_isallday_field_documents_failfast(self):
        iso = self.schema["properties"]["isAllDay"]
        assert "reminders" in iso["description"]

    def test_no_unset_leak(self):
        import json
        s = json.dumps(self.schema)
        assert "_Unset" not in s
        assert "_UNSET" not in s
        assert "PydanticUndefined" not in s


class TestUpdateTaskSchema:
    def setup_method(self):
        self.schema = _build_schema("ticktick_write", "UpdateTask")

    def test_required_taskid_projectid(self):
        assert set(self.schema["required"]) == {"taskId", "projectId"}

    def test_isallday_documents_explicit_rule(self):
        iso = self.schema["properties"]["isAllDay"]
        assert "explicitly" in iso["description"].lower()


class TestSchemaListing:
    def test_no_op_returns_listing(self):
        result = _build_schema("ticktick_write", None)
        assert "operations" in result
        assert "CreateTask" in result["operations"]
        assert "UpdateTask" in result["operations"]
        assert "hint" in result

    def test_unknown_op_raises(self):
        with pytest.raises(ValueError, match="Unknown operation"):
            _build_schema("ticktick_write", "BogusOp")
