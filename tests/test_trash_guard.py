"""Writes must refuse a task that is provably in TickTick's trash.

TickTick serves trashed tasks on GET /project/{pid}/task/{tid} with bodies
identical to live ones and silently accepts UpdateTask/CompleteTask writes to
them - the edit lands in trash and vanishes. The project listing carries only
live uncompleted tasks, so an uncompleted task missing from it can only be
trashed. Completed tasks are missing from the listing too and carry no trash
signal, so a status=2 body passes unverified.
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ticktick_mcp import tools
from ticktick_mcp.client import API_BASE, TickTickClient, TickTickError

Handler = Callable[[httpx.Request], httpx.Response]
Route = tuple[str, str]

PROJECT_DATA: Route = ("GET", "/open/v1/project/src/data")
GET_T1: Route = ("GET", "/open/v1/project/src/task/t1")
POST_TASK: Route = ("POST", "/open/v1/task")
POST_UPDATE: Route = ("POST", "/open/v1/task/t1")
POST_COMPLETE: Route = ("POST", "/open/v1/project/src/task/t1/complete")
DELETE_T1: Route = ("DELETE", "/open/v1/project/src/task/t1")

# Same adversarial shape as test_move_task.py: wire-format offset and a
# brief-less body, both of which MoveTask copies verbatim.
SRC_TASK: dict[str, Any] = {
    "id": "t1",
    "projectId": "src",
    "etag": "e-tag-1",
    "sortOrder": -1099511627776,
    "title": "Renew passport",
    "content": "no brief tag here",
    "dueDate": "2026-03-15T19:00:00.000+0400",
    "isAllDay": False,
    "priority": 3,
    "tags": ["admin", "docs"],
    "items": [{"title": "book a slot", "status": 0}],
    "status": 0,
}

COMPLETED_TASK: dict[str, Any] = {**SRC_TASK, "status": 2}


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


def listing(*task_ids: str) -> Handler:
    """GET /project/src/data - only live uncompleted tasks, as TickTick serves it."""
    tasks = [{"id": tid} for tid in task_ids]
    return reply(httpx.Response(200, json={"project": {"id": "src"}, "tasks": tasks}))


def echo_updated() -> Handler:
    """POST /task/{id} echoing the sent body back, as TickTick does."""

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        return httpx.Response(200, json={**body, "id": "t1", "projectId": "src"})

    return handler


def echo_created(project_id: str) -> Handler:
    """POST /task echoing the sent body back with a new id, as TickTick does."""

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        return httpx.Response(200, json={**body, "id": "new1", "projectId": project_id})

    return handler


def install(monkeypatch: pytest.MonkeyPatch, api: Api) -> None:
    monkeypatch.setenv("TICKTICK_ACCESS_TOKEN", "test-token")
    client = TickTickClient()
    client._http = httpx.Client(
        base_url=API_BASE,
        transport=httpx.MockTransport(api),
    )
    monkeypatch.setattr(tools, "_client", client)


class TestUpdateGuard:
    def test_update_blocked_on_ghost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("other"),
            GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
        })
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="in trash"):
            tools.update_task(taskId="t1", projectId="src", title="x")

        assert POST_UPDATE not in api.calls
        assert api.calls == [PROJECT_DATA, GET_T1]

    def test_update_passes_on_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("t1"),
            POST_UPDATE: echo_updated(),
        })
        install(monkeypatch, api)

        result = tools.update_task(taskId="t1", projectId="src", title="x")

        assert api.calls == [PROJECT_DATA, POST_UPDATE]
        assert GET_T1 not in api.calls
        assert result["title"] == "x"

    def test_update_passes_on_completed_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Documented blind spot: live-completed and trashed-completed are identical."""
        api = Api({
            PROJECT_DATA: listing(),
            GET_T1: reply(httpx.Response(200, json=COMPLETED_TASK)),
            POST_UPDATE: echo_updated(),
        })
        install(monkeypatch, api)

        result = tools.update_task(taskId="t1", projectId="src", title="x")

        assert api.calls == [PROJECT_DATA, GET_T1, POST_UPDATE]
        assert result["title"] == "x"

    def test_update_wrong_project_stays_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing(),
            GET_T1: reply(httpx.Response(200)),
        })
        install(monkeypatch, api)

        with pytest.raises(TickTickError, match="empty response body"):
            tools.update_task(taskId="t1", projectId="src", title="x")

        assert POST_UPDATE not in api.calls
        assert api.calls == [PROJECT_DATA, GET_T1]


class TestCompleteGuard:
    def test_complete_blocked_on_ghost(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("other"),
            GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
        })
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="in trash"):
            tools.complete_task(projectId="src", taskId="t1")

        assert POST_COMPLETE not in api.calls
        assert api.calls == [PROJECT_DATA, GET_T1]


class TestMoveGuard:
    def test_move_blocked_on_ghost_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("other"),
            GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
        })
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="in trash"):
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        assert POST_TASK not in api.calls
        assert DELETE_T1 not in api.calls
        assert api.calls == [PROJECT_DATA, GET_T1]

    def test_move_passes_on_live_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("t1"),
            GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("dst"),
            DELETE_T1: reply(httpx.Response(204)),
        })
        install(monkeypatch, api)

        result = tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK, DELETE_T1]
        assert api.calls[0] == PROJECT_DATA
        assert result["id"] == "new1"
        assert result["projectId"] == "dst"
