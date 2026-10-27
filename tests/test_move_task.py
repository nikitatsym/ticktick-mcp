"""MoveTask copies the task into the target project and deletes the original.

The Open API has no move: POST /task/{id} with a foreign projectId answers 2xx
with an empty body and changes nothing. The copy must be created and verified
before the original is deleted, and the payload is built straight from the API
fields returned by GetTask - wire-format dates and brief-less bodies included.
"""

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
    echo_created,
    install,
    listing,
    reply,
)

from ticktick_mcp import tools
from ticktick_mcp.client import TickTickError

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


def move_api(post: Handler, delete: Handler | None = None) -> Api:
    """t1 is live in src and readable; POST /task and DELETE behave as given."""
    routes = {
        PROJECT_DATA: listing("t1"),
        GET_T1: reply(httpx.Response(200, json=SRC_TASK)),
        POST_TASK: post,
    }
    if delete is not None:
        routes[DELETE_T1] = delete
    return Api(routes)


def move(monkeypatch: pytest.MonkeyPatch, api: Api) -> Any:
    install(monkeypatch, api)
    return tools.move_task(taskId="t1", fromProjectId="src", toProjectId="dst")


def methods(api: Api) -> list[str]:
    return [method for method, _ in api.calls]


class TestMoveTaskHappyPath:
    def test_copies_api_fields_then_deletes_original(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = move_api(echo_created("dst"), reply(httpx.Response(204)))

        result = move(monkeypatch, api)

        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK, DELETE_T1]
        assert api.bodies[2] == EXPECTED_PAYLOAD
        assert result["id"] == "new1"
        assert result["projectId"] == "dst"

    def test_non_api_fields_are_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = move_api(echo_created("dst"), reply(httpx.Response(204)))

        move(monkeypatch, api)

        sent = api.bodies[2]
        for key in ("id", "etag", "sortOrder", "status"):
            assert key not in sent
        assert sent["dueDate"] == "2026-03-15T19:00:00.000+0400"


class TestMoveTaskFailures:
    def test_create_failure_leaves_original_alone(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = move_api(reply(httpx.Response(500, json={"errorCode": "internal_error"})))

        with pytest.raises(TickTickError) as excinfo:
            move(monkeypatch, api)

        assert excinfo.value.status == 500
        assert "DELETE" not in methods(api)
        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK]

    def test_copy_landed_in_wrong_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = move_api(echo_created("somewhere-else"))

        with pytest.raises(ValueError) as excinfo:
            move(monkeypatch, api)

        msg = str(excinfo.value)
        assert "new1" in msg
        assert "NOT deleted" in msg
        assert "DELETE" not in methods(api)
        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK]

    def test_delete_failure_names_both_copies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = move_api(echo_created("dst"), reply(httpx.Response(500, json={"errorCode": "internal_error"})))

        with pytest.raises(TickTickError) as excinfo:
            move(monkeypatch, api)

        msg = str(excinfo.value)
        assert "new1" in msg
        assert "t1" in msg
        assert "NOT deleted" in msg
        assert api.calls == [PROJECT_DATA, GET_T1, POST_TASK, DELETE_T1]

    def test_same_project_makes_no_requests(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({})
        install(monkeypatch, api)

        with pytest.raises(ValueError, match="already in"):
            tools.move_task(taskId="t1", fromProjectId="src", toProjectId="src")

        assert api.calls == []

    def test_empty_source_body_fails_before_create(self, monkeypatch: pytest.MonkeyPatch) -> None:
        api = Api({
            PROJECT_DATA: listing("t1"),
            GET_T1: reply(httpx.Response(200)),
        })

        with pytest.raises(TickTickError) as excinfo:
            move(monkeypatch, api)

        assert "empty response body" in str(excinfo.value)
        assert api.calls == [PROJECT_DATA, GET_T1]
