"""Expected failures reach the MCP caller as result data, not as exceptions.

An exception crossing the tool boundary is reported by MCP clients as a
contextless execution failure, so the TickTick status, the failing request, and
the offending parameter would all be lost. Parameter-validation coverage lives
in test_strict_validation.py; this file pins the API, transport, and
programming-error edges.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest

from ticktick_mcp import server
from ticktick_mcp.client import TickTickError
from ticktick_mcp.server import _dispatch


@pytest.fixture()
def mock_client() -> Iterator[MagicMock]:
    client = MagicMock()
    with patch("ticktick_mcp.tools._get_client", return_value=client):
        yield client


def test_api_error_keeps_status_method_path_and_body(mock_client: MagicMock) -> None:
    mock_client.get_project.side_effect = TickTickError(
        404, "GET", "/open/v1/project/p1", {"errorCode": "project_not_found"}
    )

    result = _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})

    assert result == {
        "error": (
            "TickTick API 404 GET /open/v1/project/p1: "
            "{'errorCode': 'project_not_found'}"
        )
    }


def test_transport_error_names_request_without_query(mock_client: MagicMock) -> None:
    request = httpx.Request(
        "GET", "https://api.ticktick.com/open/v1/project/p1?token=must-not-leak"
    )
    mock_client.get_project.side_effect = httpx.ConnectError(
        "Connection refused", request=request
    )

    result = _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})

    assert result == {
        "error": (
            "TickTick request failed: GET /open/v1/project/p1: "
            "ConnectError: Connection refused"
        )
    }
    assert "must-not-leak" not in repr(result)


def test_missing_required_param_reports_the_field(mock_client: MagicMock) -> None:
    result = _dispatch("GetProject", "ticktick_read", {})

    assert "projectId" in result["error"]
    mock_client.get_project.assert_not_called()


def test_registered_group_reports_invalid_help_input() -> None:
    group_tool = server.mcp._tool_manager._tools["ticktick_read"].fn

    result = group_tool(operation="help", params={"search": 1})

    assert result == {"error": "help parameter 'search' must be a string"}


def test_programming_error_still_propagates(mock_client: MagicMock) -> None:
    """A bug must stay a crash: only expected failures become result data."""
    mock_client.get_project.side_effect = TypeError("slim_task() got an int")

    with pytest.raises(TypeError):
        _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})
