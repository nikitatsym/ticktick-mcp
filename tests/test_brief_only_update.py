"""Brief-only UpdateTask: caller passes `brief` without `content`.

The wrapper must fetch the existing task body and rewrite only the <brief>
tag — passing brief alone must NOT clobber the rest of the body. This is the
behaviour the original tools.py:186-188 implemented; v2.5 preserves it.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from ticktick_mcp.server import _dispatch


@pytest.fixture()
def mock_client() -> Iterator[MagicMock]:
    client = MagicMock()
    with patch("ticktick_mcp.tools._get_client", return_value=client):
        yield client


def test_brief_only_update_fetches_existing(mock_client: MagicMock) -> None:
    mock_client.get_task.return_value = {
        "id": "t1",
        "projectId": "p1",
        "content": "existing body text",
    }
    mock_client.update_task.return_value = {
        "id": "t1",
        "projectId": "p1",
        "title": "X",
    }
    _dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1", "brief": "fresh summary",
    })
    mock_client.get_task.assert_called_once_with("p1", "t1")
    sent = mock_client.update_task.call_args[0][1]
    assert "<brief>fresh summary</brief>" in sent["content"]
    assert "existing body text" in sent["content"]


def test_brief_and_content_does_not_fetch(mock_client: MagicMock) -> None:
    mock_client.update_task.return_value = {
        "id": "t1", "projectId": "p1",
    }
    _dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1",
        "brief": "summary", "content": "wholly new body",
    })
    mock_client.get_task.assert_not_called()
    sent = mock_client.update_task.call_args[0][1]
    assert "<brief>summary</brief>" in sent["content"]
    assert "wholly new body" in sent["content"]


def test_empty_brief_raises_before_fetch(mock_client: MagicMock) -> None:
    with pytest.raises(ValueError, match="brief parameter must be non-empty"):
        _dispatch("UpdateTask", "ticktick_write", {
            "taskId": "t1", "projectId": "p1", "brief": "",
        })
    mock_client.get_task.assert_not_called()
    mock_client.update_task.assert_not_called()


def test_no_brief_no_content_no_fetch(mock_client: MagicMock) -> None:
    """Update with only a title change — no fetch, no brief validation."""
    mock_client.update_task.return_value = {"id": "t1", "projectId": "p1", "title": "New"}
    _dispatch("UpdateTask", "ticktick_write", {
        "taskId": "t1", "projectId": "p1", "title": "New",
    })
    mock_client.get_task.assert_not_called()
    sent = mock_client.update_task.call_args[0][1]
    assert sent["title"] == "New"
    assert "content" not in sent
