"""Help text v2.5: per-param bullets, `?` markers, timezone banner, cross-group hints."""

import pytest

from ticktick_mcp.server import _build_help


def test_help_lists_all_write_ops() -> None:
    text = _build_help("ticktick_write")
    for op in ("CreateTask", "UpdateTask", "CompleteTask", "CreateProject", "UpdateProject"):
        assert op in text
    assert "5 operations available." in text


def test_help_lists_all_read_ops() -> None:
    text = _build_help("ticktick_read")
    for op in ("GetToday", "GetInbox", "GetInboxId", "ListProjects",
               "GetProject", "GetProjectWithData", "GetTask"):
        assert op in text
    assert "7 operations available." in text


def test_help_per_param_description_bullets() -> None:
    text = _build_help("ticktick_write")
    # CreateTask brief field has a description set
    assert "brief: One-liner stored as <brief>summary</brief>" in text
    # CreateTask timeZone description names the fallback explicitly
    assert "timeZone: IANA name" in text


def test_help_pointer_to_schema() -> None:
    text = _build_help("ticktick_write")
    assert "operation='schema'" in text


def test_help_write_banner_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_TICKTICK_TIMEZONE", raising=False)
    text = _build_help("ticktick_write")
    assert "Timezone fallback (MCP_TICKTICK_TIMEZONE):" in text
    assert "unset" in text
    assert "timeZone parameter is required" in text


def test_help_write_banner_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TICKTICK_TIMEZONE", "Asia/Tbilisi")
    text = _build_help("ticktick_write")
    assert "Asia/Tbilisi" in text
    assert "_used_timezone" in text


def test_help_write_banner_unset_includes_system_tz_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_TICKTICK_TIMEZONE", raising=False)
    monkeypatch.setattr("ticktick_mcp.server.system_timezone", lambda: "Europe/Berlin")
    text = _build_help("ticktick_write")
    assert "'Europe/Berlin'" in text
    assert "confirm with the user" in text


def test_help_write_banner_unset_no_system_tz(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MCP_TICKTICK_TIMEZONE", raising=False)
    monkeypatch.setattr("ticktick_mcp.server.system_timezone", lambda: None)
    text = _build_help("ticktick_write")
    assert "could not be detected" in text


def test_help_write_banner_set_no_system_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MCP_TICKTICK_TIMEZONE", "Asia/Tbilisi")
    monkeypatch.setattr("ticktick_mcp.server.system_timezone", lambda: "Europe/Berlin")
    text = _build_help("ticktick_write")
    assert "System timezone" not in text


def test_help_read_no_banner() -> None:
    text = _build_help("ticktick_read")
    assert "Timezone fallback" not in text


def test_help_search_filters() -> None:
    text = _build_help("ticktick_write", search="project")
    assert "CreateProject" in text
    assert "UpdateProject" in text
    assert "CreateTask" not in text


def test_help_search_cross_group_hint() -> None:
    """Searching 'task' in read should surface write/delete ops via hint."""
    text = _build_help("ticktick_read", search="delete")
    # No read ops match 'delete', but DeleteTask/DeleteProject do in ticktick_delete
    assert "ticktick_delete" in text


def test_help_search_no_match_message() -> None:
    text = _build_help("ticktick_read", search="bogusxyz")
    assert "No ops in ticktick_read matching 'bogusxyz'" in text


def test_help_question_marker_for_optional() -> None:
    text = _build_help("ticktick_write")
    # CreateTask projectId is optional (_UNSET default) — should render with ?
    assert "projectId?:" in text


def test_help_required_no_marker() -> None:
    text = _build_help("ticktick_write")
    # CreateTask title is required
    assert "title: str" in text


@pytest.mark.parametrize("sentinel", ["_Unset", "_UNSET", "PydanticUndefined"])
def test_no_sentinel_leakage(sentinel: str) -> None:
    for group in ("ticktick_read", "ticktick_write", "ticktick_delete"):
        text = _build_help(group)
        assert sentinel not in text
