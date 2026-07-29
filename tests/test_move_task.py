"""MoveTask copies the task into the target project and deletes the original.

The Open API has no move: POST /task/{id} with a foreign projectId answers 2xx
with an empty body and changes nothing. The copy must be created and verified
before the original is deleted, and the payload is built straight from the API
fields returned by GetTask - wire-format dates and brief-less bodies included.
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

GET_SRC: Route = ("GET", "/open/v1/project/src/task/t1")
POST_TASK: Route = ("POST", "/open/v1/task")
DELETE_SRC: Route = ("DELETE", "/open/v1/project/src/task/t1")

# Adversarial on purpose: the manual +0400 offset and the brief-less content
# are both rejected by _prepare_task, which MoveTask must bypass.
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
}

EXPECTED_PAYLOAD: dict[str, Any] = {
    "title": "Renew passport",
    "projectId": "dst",
    "content": "no brief tag here",
    "dueDate": "2026-03-15T19:00:00.000+0400",
    "isAllDay": False,
    "priority": 3,
    "tags": ["admin", "docs"],
    "items": [{"title": "book a slot", "status": 0}],
}


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


def methods(api: Api) -> list[str]:
    return [method for method, _ in api.calls]


class TestMoveTaskHappyPath:
    def test_copies_api_fields_then_deletes_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            GET_SRC: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("dst"),
            DELETE_SRC: reply(httpx.Response(204)),
        })
        install(monkeypatch, api)

        result = tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        assert api.calls == [GET_SRC, POST_TASK, DELETE_SRC]
        assert api.bodies[1] == EXPECTED_PAYLOAD
        assert result["id"] == "new1"
        assert result["projectId"] == "dst"

    def test_non_api_fields_are_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            GET_SRC: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("dst"),
            DELETE_SRC: reply(httpx.Response(204)),
        })
        install(monkeypatch, api)

        tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        sent = api.bodies[1]
        for key in ("id", "etag", "sortOrder"):
            assert key not in sent
        assert sent["dueDate"] == "2026-03-15T19:00:00.000+0400"


class TestMoveTaskFailures:
    def test_create_failure_leaves_original_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            GET_SRC: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: reply(httpx.Response(500, json={"errorCode": "internal_error"})),
        })
        install(monkeypatch, api)

        with pytest.raises(TickTickError) as excinfo:
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        assert excinfo.value.status == 500
        assert "DELETE" not in methods(api)
        assert api.calls == [GET_SRC, POST_TASK]

    def test_copy_landed_in_wrong_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            GET_SRC: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("somewhere-else"),
        })
        install(monkeypatch, api)

        with pytest.raises(ValueError) as excinfo:
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        msg = str(excinfo.value)
        assert "new1" in msg
        assert "NOT deleted" in msg
        assert "DELETE" not in methods(api)

    def test_delete_failure_names_both_copies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            GET_SRC: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("dst"),
            DELETE_SRC: reply(httpx.Response(500, json={"errorCode": "internal_error"})),
        })
        install(monkeypatch, api)

        with pytest.raises(TickTickError) as excinfo:
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        msg = str(excinfo.value)
        assert "new1" in msg
        assert "t1" in msg
        assert "NOT deleted" in msg
        assert api.calls == [GET_SRC, POST_TASK, DELETE_SRC]

    def test_same_project_makes_no_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({})
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="already in"):
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="src")

        assert api.calls == []

    def test_empty_source_body_fails_before_create(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({GET_SRC: reply(httpx.Response(200))})
        install(monkeypatch, api)

        with pytest.raises(TickTickError) as excinfo:
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")

        assert "empty response body" in str(excinfo.value)
        assert api.calls == [GET_SRC]
