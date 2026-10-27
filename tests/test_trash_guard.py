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
from api_fixtures import (
    DELETE_T1,
    GET_T1,
    POST_TASK,
    PROJECT_DATA,
    SRC_TASK,
    Api,
    Handler,
    Route,
    echo_created,
    install,
    listing,
    reply,
)

from ticktick_mcp import tools
from ticktick_mcp.client import TickTickError

POST_UPDATE: Route = ("POST", "/open/v1/task/t1")
POST_COMPLETE: Route = ("POST", "/open/v1/project/src/task/t1/complete")

COMPLETED_TASK: dict[str, Any] = {**SRC_TASK, "status": 2}


def echo_updated() -> Handler:
    """POST /task/{id} echoing the sent body back, as TickTick does."""

    def handler(request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content)
        return httpx.Response(200, json={**body, "id": "t1", "projectId": "src"})

    return handler


def update() -> Any:
    return tools.update_task(taskId="t1", projectId="src", title="x")


def complete() -> Any:
    return tools.complete_task(projectId="src", taskId="t1")


def move() -> Any:
    return tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")


@pytest.mark.parametrize(
    ("write", "forbidden"),
    [
        pytest.param(update, [POST_UPDATE], id="update"),
        pytest.param(complete, [POST_COMPLETE], id="complete"),
        pytest.param(move, [POST_TASK, DELETE_T1], id="move"),
    ],
)
def test_write_blocked_on_ghost(
    monkeypatch: pytest.MonkeyPatch,
    write: Callable[[], object],
    forbidden: list[Route],
) -> None:
    api = Api({
        PROJECT_DATA: listing("other"),
        GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
    })
    install(monkeypatch, api)

    with pytest.raises(ValueError, match="in trash"):
        write()

    for route in forbidden:
        assert route not in api.calls
    assert api.calls == [PROJECT_DATA, GET_T1]


class TestUpdateGuard:
    def test_update_passes_on_live(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("t1"),
            POST_UPDATE: echo_updated(),
        })
        install(monkeypatch, api)

        result = update()

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

        result = update()

        assert api.calls == [PROJECT_DATA, GET_T1, POST_UPDATE]
        assert result["title"] == "x"

    def test_update_wrong_project_stays_loud(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing(),
            GET_T1: reply(httpx.Response(200)),
        })
        install(monkeypatch, api)

        with pytest.raises(TickTickError, match="empty response body"):
            update()

        assert POST_UPDATE not in api.calls
        assert api.calls == [PROJECT_DATA, GET_T1]


class TestMoveGuard:
    def test_move_passes_on_live_source(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("t1"),
            GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
            POST_TASK: echo_created("dst"),
            DELETE_T1: reply(httpx.Response(204)),
        })
        install(monkeypatch, api)

        result = move()

        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK, DELETE_T1]
        assert result["id"] == "new1"
        assert result["projectId"] == "dst"
