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

from pydantic_settings import BaseSettings


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
