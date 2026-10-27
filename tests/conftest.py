"""Shared pytest fixtures.

The autouse fixture drops the cached settings and the OS timezone before and
after every test so `monkeypatch.setenv(...)` reliably reaches `get_settings()`.
"""

from collections.abc import Iterator

import pytest

from ticktick_mcp import config


@pytest.fixture(autouse=True)
def reset_settings() -> Iterator[None]:
    config._settings = None
    config.system_timezone.cache_clear()
    yield
    config._settings = None
    config.system_timezone.cache_clear()
