"""Shared pytest fixtures.

`reset_settings` autouse fixture clears the lazy `_settings` cache before
every test so `monkeypatch.setenv(...)` reliably propagates through
`get_settings()` without test ordering issues.
"""

import pytest

from ticktick_mcp.config import _reset_settings


@pytest.fixture(autouse=True)
def reset_settings():
    _reset_settings()
    yield
    _reset_settings()
