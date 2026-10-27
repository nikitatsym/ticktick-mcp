"""Mock TickTick API shared by the tests that drive tools through a real client."""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ticktick_mcp import tools
from ticktick_mcp.client import API_BASE, TickTickClient

Handler = Callable[[httpx.Request], httpx.Response]
Route = tuple[str, str]

PROJECT_DATA: Route = ("GET", "/open/v1/project/src/data")
GET_T1: Route = ("GET", "/open/v1/project/src/task/t1")
POST_TASK: Route = ("POST", "/open/v1/task")
DELETE_T1: Route = ("DELETE", "/open/v1/project/src/task/t1")

# Adversarial on purpose: the manual +0400 offset and the brief-less content
# are both rejected by prepare_task, which MoveTask must bypass.
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
