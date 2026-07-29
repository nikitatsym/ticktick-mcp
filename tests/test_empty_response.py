"""Empty 2xx bodies where JSON is expected must fail at the client, not downstream.

TickTick answers 2xx with an empty body for a rejected no-op write (e.g. POST
/task/{id} moving projectId) and for GET /project/{pid}/task/{tid} when the task
lives in another project. Those used to return None and blow up far from the cause.
"""

from collections.abc import Callable

import httpx
import pytest

from ticktick_mcp.client import API_BASE, TickTickClient, TickTickError
from ticktick_mcp.prepare import _verify_response

Handler = Callable[[httpx.Request], httpx.Response]


def make_client(monkeypatch: pytest.MonkeyPatch, handler: Handler) -> TickTickClient:
    monkeypatch.setenv("TICKTICK_ACCESS_TOKEN", "test-token")
    client = TickTickClient()
    client._http = httpx.Client(
        base_url=API_BASE,
        transport=httpx.MockTransport(handler),
    )
    return client


def empty_body(status: int) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status)

    return handler


class TestEmptyBodyOnJsonPath:
    def test_create_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = make_client(monkeypatch, empty_body(200))
        with pytest.raises(TickTickError) as excinfo:
            client.create_task({"title": "T"})
        msg = str(excinfo.value)
        assert "200" in msg
        assert "POST" in msg
        assert "/task" in msg
        assert "empty response body" in msg

    def test_update_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = make_client(monkeypatch, empty_body(200))
        with pytest.raises(TickTickError) as excinfo:
            client.update_task("t1", {"projectId": "p2"})
        assert "/task/t1" in str(excinfo.value)

    def test_get_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = make_client(monkeypatch, empty_body(200))
        with pytest.raises(TickTickError) as excinfo:
            client.get_task("p1", "t1")
        assert "empty response body" in str(excinfo.value)

    def test_create_project(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = make_client(monkeypatch, empty_body(200))
        with pytest.raises(TickTickError) as excinfo:
            client.create_project({"name": "P"})
        assert "empty response body" in str(excinfo.value)

    def test_list_projects(self, monkeypatch: pytest.MonkeyPatch) -> None:
        client = make_client(monkeypatch, empty_body(200))
        with pytest.raises(TickTickError) as excinfo:
            client.list_projects()
        assert "empty response body" in str(excinfo.value)

    def test_list_projects_empty_json_list(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=[])

        client = make_client(monkeypatch, handler)
        assert client.list_projects() == []


class TestNoContentPath:
    def test_delete_task_204(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(f"{request.method} {request.url.path}")
            return httpx.Response(204)

        client = make_client(monkeypatch, handler)
        client.delete_task("p1", "t1")
        assert seen == ["DELETE /open/v1/project/p1/task/t1"]

    def test_complete_task_200_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(f"{request.method} {request.url.path}")
            return httpx.Response(200)

        client = make_client(monkeypatch, handler)
        client.complete_task("p1", "t1")
        assert seen == ["POST /open/v1/project/p1/task/t1/complete"]


class TestErrorStatusStillCarriesBody:
    def test_404_with_json_body(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404, json={"errorCode": "task_not_found"})

        client = make_client(monkeypatch, handler)
        with pytest.raises(TickTickError) as excinfo:
            client.get_task("p1", "t1")
        assert excinfo.value.status == 404
        assert excinfo.value.body == {"errorCode": "task_not_found"}


class TestVerifyResponseNonDict:
    def test_list_response(self) -> None:
        with pytest.raises(ValueError, match="cannot verify"):
            _verify_response({"title": "x"}, ["not", "a", "dict"])

    def test_string_response(self) -> None:
        with pytest.raises(ValueError, match="cannot verify"):
            _verify_response({"title": "x"}, "not a dict")
