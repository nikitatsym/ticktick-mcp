"""The zone comes only from an explicit timeZone parameter.

No env var, no system zone, no silent UTC: a missing zone is an error, and
GetToday computes the day boundaries in the zone the caller passes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, tzinfo
from typing import Any

import httpx
import pytest

from ticktick_mcp import tools
from ticktick_mcp.client import API_BASE, TickTickClient
from ticktick_mcp.config import get_settings
from ticktick_mcp.prepare import _prepare_task
from ticktick_mcp.server import _build_schema

Handler = Callable[[httpx.Request], httpx.Response]
Route = tuple[str, str]

LIST_PROJECTS: Route = ("GET", "/open/v1/project")
POST_TASK: Route = ("POST", "/open/v1/task")
DELETE_PROBE: Route = ("DELETE", "/open/v1/project/inbox/task/probe")
INBOX_DATA: Route = ("GET", "/open/v1/project/inbox/data")


class Api:
    """MockTransport backend: records (method, path) in order, replies per route."""

    def __init__(self, routes: dict[Route, Handler]) -> None:
        self.routes = routes
        self.calls: list[Route] = []
        self.bodies: list[Any] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        key: Route = (request.method, request.url.path)
        self.calls.append(key)
        self.bodies.append(json.loads(request.content) if request.content else None)
        handler = self.routes.get(key)
        if handler is None:
            raise AssertionError(f"unrouted request {key}")
        return handler(request)


def reply(response: httpx.Response) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return response

    return handler


def install(monkeypatch: pytest.MonkeyPatch, api: Api) -> None:
    monkeypatch.setenv("TICKTICK_ACCESS_TOKEN", "test-token")
    client = TickTickClient()
    client._http = httpx.Client(
        base_url=API_BASE,
        transport=httpx.MockTransport(api),
    )
    monkeypatch.setattr(tools, "_client", client)


def inbox_only(tasks: list[dict[str, Any]]) -> Api:
    """No projects; the inbox probe resolves to project 'inbox' holding `tasks`."""
    return Api({
        LIST_PROJECTS: reply(httpx.Response(200, json=[])),
        POST_TASK: reply(httpx.Response(200, json={"id": "probe", "projectId": "inbox"})),
        DELETE_PROBE: reply(httpx.Response(204)),
        INBOX_DATA: reply(httpx.Response(200, json={"tasks": tasks})),
    })


class FrozenDatetime(datetime):
    """Clock pinned to 2026-07-15 12:00 in whatever zone the caller asks for."""

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> FrozenDatetime:
        return cls(2026, 7, 15, 12, 0, tzinfo=tz)


def freeze(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("ticktick_mcp.client.datetime", FrozenDatetime)


def ids(tasks: list[Any]) -> list[str]:
    return [str(t["id"]) for t in tasks]


# -- No fallback of any kind --------------------------------------------------


class TestNoFallback:
    def test_env_var_is_dead(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The env var may be set in the environment; it must change nothing."""
        monkeypatch.setenv("MCP_TICKTICK_TIMEZONE", "Europe/Berlin")
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15T19:00"})
        msg = str(exc.value)
        assert "no timeZone" in msg
        assert "MCP_TICKTICK_TIMEZONE" not in msg

    def test_settings_field_removed(self) -> None:
        assert not hasattr(get_settings(), "mcp_ticktick_timezone")

    def test_param_still_normalizes(self) -> None:
        task = _prepare_task({
            "title": "T", "brief": "B",
            "dueDate": "2026-03-15T19:00", "timeZone": "Europe/Berlin",
        })
        assert isinstance(task, dict)
        assert task["dueDate"].endswith("+0100")

    def test_hint_softened(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ticktick_mcp.prepare.system_timezone", lambda: "Europe/Berlin")
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15T19:00"})
        msg = str(exc.value)
        assert "container artifact" in msg
        assert "Europe/Berlin" in msg

    def test_no_hint_without_system_zone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("ticktick_mcp.prepare.system_timezone", lambda: None)
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "dueDate": "2026-03-15T19:00"})
        msg = str(exc.value)
        assert "System timezone" not in msg
        assert "no timeZone" in msg

    def test_unknown_zone_message_has_no_tbilisi(self) -> None:
        with pytest.raises(ValueError) as exc:
            _prepare_task({"title": "T", "brief": "B", "timeZone": "Nope/Nope"})
        msg = str(exc.value)
        assert "Unknown timezone" in msg
        assert "Tbilisi" not in msg


# -- GetToday day boundaries in the passed zone -------------------------------


class TestGetTodayInPassedZone:
    def test_allday_tomorrow_negative_zone_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Tomorrow's all-day midnight falls inside local today by instant, at UTC-8."""
        freeze(monkeypatch)
        api = inbox_only([
            {"id": "a1", "isAllDay": True, "status": 0, "title": "x",
             "dueDate": "2026-07-16T00:00:00.000+0000"},
        ])
        install(monkeypatch, api)

        assert tools.get_today(timeZone="Etc/GMT+8") == []

    def test_allday_today_and_overdue_included(self, monkeypatch: pytest.MonkeyPatch) -> None:
        freeze(monkeypatch)
        api = inbox_only([
            {"id": "a1", "isAllDay": True, "status": 0, "title": "today",
             "dueDate": "2026-07-15T00:00:00.000+0000"},
            {"id": "a2", "isAllDay": True, "status": 0, "title": "overdue",
             "dueDate": "2026-07-14T00:00:00.000+0000"},
        ])
        install(monkeypatch, api)

        assert sorted(ids(tools.get_today(timeZone="Etc/GMT+8"))) == ["a1", "a2"]

    def test_timed_tomorrow_positive_zone_excluded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """At UTC+4 the old UTC boundary would have swallowed tomorrow 01:00 local."""
        freeze(monkeypatch)
        api = inbox_only([
            {"id": "t1", "isAllDay": False, "status": 0, "title": "tomorrow",
             "dueDate": "2026-07-16T01:00:00.000+0400"},
            {"id": "t2", "isAllDay": False, "status": 0, "title": "tonight",
             "dueDate": "2026-07-15T23:00:00.000+0400"},
        ])
        install(monkeypatch, api)

        assert ids(tools.get_today(timeZone="Etc/GMT-4")) == ["t2"]

    def test_gettoday_requires_valid_zone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = inbox_only([])
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="Unknown timezone"):
            tools.get_today(timeZone="Nope/Nope")

        assert api.calls == []

    def test_gettoday_schema_requires_timezone(self) -> None:
        schema = _build_schema("ticktick_read", "GetToday")
        assert schema["required"] == ["timeZone"]
