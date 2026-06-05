"""The `_UNSET` sentinel must:
  1. survive Pydantic model build via cast(T, _UNSET) → default_factory
  2. NOT appear in dispatched kwargs (`model_dump(exclude_unset=True)` strips it)
  3. NOT leak into JSON Schema or help-text rendering
"""

import json

from ticktick_mcp import tools as _tools_module
from ticktick_mcp.registry import _UNSET, _Unset
from ticktick_mcp.server import _build_help, _build_schema


def test_unset_singleton():
    assert _UNSET is _Unset()


def test_unset_is_falsy():
    assert not _UNSET


def test_unset_not_in_dispatched_kwargs():
    """model.model_validate({}) → model_dump(exclude_unset=True) drops the sentinel."""
    model = getattr(_tools_module.create_task, "_params_model")
    validated = model.model_validate({"title": "T", "brief": "B"})
    dumped = validated.model_dump(exclude_unset=True)
    assert "title" in dumped
    assert "brief" in dumped
    # Every optional param defaulted to _UNSET must be absent
    for k in ("projectId", "content", "desc", "startDate", "dueDate",
              "isAllDay", "priority", "tags", "timeZone", "reminders",
              "repeatFlag", "items"):
        assert k not in dumped, f"{k} leaked into dispatched kwargs"
    for v in dumped.values():
        assert v is not _UNSET


def test_unset_not_in_schema():
    schema = _build_schema("ticktick_write", "CreateTask")
    s = json.dumps(schema)
    assert "_Unset" not in s
    assert "_UNSET" not in s
    assert "PydanticUndefined" not in s


def test_unset_not_in_help():
    text = _build_help("ticktick_write")
    assert "_Unset" not in text
    assert "_UNSET" not in text
    assert "PydanticUndefined" not in text


def test_optional_params_render_with_question_mark():
    text = _build_help("ticktick_write")
    # CreateTask has brief? content? projectId? all optional via _UNSET
    assert "brief?:" in text
    assert "content?:" in text
    assert "projectId?:" in text


def test_required_params_render_without_question_mark():
    text = _build_help("ticktick_write")
    # CreateTask title is required (no _UNSET default)
    # CompleteTask projectId/taskId are required
    assert "title: str" in text
    assert "taskId: str" in text
