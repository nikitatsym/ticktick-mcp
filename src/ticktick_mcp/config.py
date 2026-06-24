"""Centralized configuration via pydantic-settings.

All env vars currently read elsewhere flow through `get_settings()`:

  TICKTICK_CLIENT_ID         — OAuth client id (was: tools.py:_get_client)
  TICKTICK_CLIENT_SECRET     — OAuth client secret (was: tools.py:_get_client)
  TICKTICK_ACCESS_TOKEN      — bearer token (was: auth.py)
  MCP_TICKTICK_BRIEF_MAX     — brief tag length cap; 0 disables enforcement
  MCP_TICKTICK_TIMEZONE      — IANA name fallback used when a caller passes a
                               time-of-day with no `timeZone` param. Promoted
                               to first-class config so help/schema/echo can
                               surface its current value to the agent.
"""

from __future__ import annotations

from functools import lru_cache

import tzlocal
from pydantic_settings import BaseSettings
from zoneinfo import ZoneInfoNotFoundError


class Settings(BaseSettings):
    ticktick_client_id: str = ""
    ticktick_client_secret: str = ""
    ticktick_access_token: str = ""
    mcp_ticktick_brief_max: int = 100
    mcp_ticktick_timezone: str = ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def _reset_settings() -> None:
    """Force re-read from env. Used by tests after monkeypatching."""
    global _settings
    _settings = None
    system_timezone.cache_clear()


@lru_cache(maxsize=1)
def system_timezone() -> str | None:
    """IANA name of the OS timezone, or None if it can't be determined.

    Surfaced as a hint in help/error text. Never used as a silent fallback —
    callers must still pass `timeZone` or set MCP_TICKTICK_TIMEZONE.
    """
    try:
        return tzlocal.get_localzone().key
    except ZoneInfoNotFoundError:
        return None
