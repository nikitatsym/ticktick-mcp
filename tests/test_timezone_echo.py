"""Failure mode #3: silent timezone fallback.

`_prepare_task` returns `(task, tz_meta)`; `tz_meta` is emitted whenever a
zone was resolved (time-of-day normalized OR explicit timeZone param passed).
The wrapper attaches it as `_used_timezone` so the agent can verify.
"""

import pytest

from ticktick_mcp.prepare import _prepare_task


class TestTzMetaEmit:
    def test_emit_on_explicit_param_with_time(self) -> None:
        _task, tz = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-03-15T19:00",
            "timeZone": "Europe/Berlin",
        })
        assert tz == {"used": "Europe/Berlin", "source": "param"}

    def test_emit_on_env_fallback_with_time(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MCP_TICKTICK_TIMEZONE", "Asia/Tbilisi")
        _task, tz = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-06-10T13:00",
        })
        assert tz == {"used": "Asia/Tbilisi", "source": "env:MCP_TICKTICK_TIMEZONE"}

    def test_emit_on_explicit_param_no_date(self) -> None:
        """timeZone passed by itself (e.g. updating only timezone) should still echo."""
        _task, tz = _prepare_task(
            {"projectId": "p1", "timeZone": "Europe/Berlin"}, is_update=True
        )
        assert tz == {"used": "Europe/Berlin", "source": "param"}


class TestTzMetaNone:
    def test_none_on_dateonly_no_param(self) -> None:
        _task, tz = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15"})
        assert tz is None

    def test_none_on_no_date_no_param(self) -> None:
        _task, tz = _prepare_task({"title": "T", "brief": "B"})
        assert tz is None

    def test_none_on_dateonly_with_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Env var set but no time-of-day and no explicit param → no echo."""
        monkeypatch.setenv("MCP_TICKTICK_TIMEZONE", "Asia/Tbilisi")
        _task, tz = _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15"})
        assert tz is None


class TestMissingTzErrorHint:
    def test_error_includes_system_tz_hint(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_TICKTICK_TIMEZONE", raising=False)
        monkeypatch.setattr("ticktick_mcp.prepare.system_timezone", lambda: "Europe/Berlin")
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15T19:00"})
        msg = str(exc.value)
        assert "'Europe/Berlin'" in msg
        assert "confirm with the user" in msg

    def test_error_without_hint_when_system_tz_undetected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MCP_TICKTICK_TIMEZONE", raising=False)
        monkeypatch.setattr("ticktick_mcp.prepare.system_timezone", lambda: None)
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15T19:00"})
        msg = str(exc.value)
        assert "System timezone" not in msg
        assert "no timeZone" in msg
