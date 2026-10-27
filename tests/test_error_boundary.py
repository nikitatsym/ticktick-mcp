"""Expected failures reach the MCP caller as failed tool results with their cause.

`_dispatch` raises a ToolError carrying the TickTick status, the failing
request, or the offending parameter, redacted of credentials and query values.
Parameter-validation coverage lives in test_strict_validation.py; this file pins
the API, transport, wire, and programming-error edges.
"""

import asyncio
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import httpx
import pytest
from mcp.client import Client
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent

from ticktick_mcp import server
from ticktick_mcp.client import TickTickError
from ticktick_mcp.server import _dispatch


@pytest.fixture()
def mock_client() -> Iterator[MagicMock]:
    client = MagicMock()
    with patch("ticktick_mcp.tools._get_client", return_value=client):
        yield client


def call_over_mcp(tool: str, arguments: dict[str, object]) -> CallToolResult:
    async def call() -> CallToolResult:
        async with Client(server.mcp) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(call())


def test_api_error_keeps_status_method_path_and_body(mock_client: MagicMock) -> None:
    mock_client.get_project.side_effect = TickTickError(
        404, "GET", "/open/v1/project/p1", {"errorCode": "project_not_found"}
    )

    with pytest.raises(ToolError) as excinfo:
        _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})

    assert str(excinfo.value) == (
        "TickTick API 404 GET /open/v1/project/p1: {'errorCode': 'project_not_found'}"
    )
    assert isinstance(excinfo.value.__cause__, TickTickError)


def test_transport_error_names_request_without_query(mock_client: MagicMock) -> None:
    request = httpx.Request(
        "GET", "https://api.ticktick.com/open/v1/project/p1?token=must-not-leak"
    )
    mock_client.get_project.side_effect = httpx.ConnectError(
        "Connection refused", request=request
    )

    with pytest.raises(ToolError) as excinfo:
        _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})

    assert str(excinfo.value) == (
        "TickTick request failed: GET /open/v1/project/p1: ConnectError: Connection refused"
    )
    assert "must-not-leak" not in str(excinfo.value)


def test_missing_required_param_reports_the_field(mock_client: MagicMock) -> None:
    with pytest.raises(ToolError, match="projectId"):
        _dispatch("GetProject", "ticktick_read", {})

    mock_client.get_project.assert_not_called()


def test_failure_is_an_error_result_on_the_wire(mock_client: MagicMock) -> None:
    mock_client.get_project.side_effect = TickTickError(
        401, "GET", "/open/v1/project/p1?access_token=must-not-leak", {"error": "unauthorized"}
    )

    result = call_over_mcp("ticktick_read", {"operation": "GetProject", "params": {"projectId": "p1"}})

    assert result.is_error is True
    assert len(result.content) == 1
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert "TickTick API 401 GET /open/v1/project/p1" in text.text
    assert "must-not-leak" not in text.text


def test_invalid_help_input_is_an_error_result_on_the_wire() -> None:
    result = call_over_mcp("ticktick_read", {"operation": "help", "params": {"search": 1}})

    assert result.is_error is True
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert "help parameter 'search' must be a string" in text.text


def test_success_is_not_an_error_result_on_the_wire(mock_client: MagicMock) -> None:
    mock_client.get_project.return_value = {"id": "p1", "name": "Work"}

    result = call_over_mcp("ticktick_read", {"operation": "GetProject", "params": {"projectId": "p1"}})

    assert result.is_error is False
    text = result.content[0]
    assert isinstance(text, TextContent)
    assert text.text == '{"id":"p1","name":"Work"}'


def test_programming_error_still_propagates(mock_client: MagicMock) -> None:
    """A bug must stay a crash, not be dressed up as an expected failure."""
    mock_client.get_project.side_effect = TypeError("slim_task() got an int")

    with pytest.raises(TypeError):
        _dispatch("GetProject", "ticktick_read", {"projectId": "p1"})
