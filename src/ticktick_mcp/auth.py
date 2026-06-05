"""OAuth metadata + bearer token resolver."""

from __future__ import annotations

from .config import get_settings

REDIRECT_URI = "https://nikitatsym.github.io/ticktick-mcp/"
SCOPES = "tasks:read tasks:write"


def get_access_token() -> str:
    token = get_settings().ticktick_access_token
    if token:
        return token
    raise RuntimeError(
        "No authentication token found.\n"
        "Set TICKTICK_ACCESS_TOKEN environment variable.\n"
        "Visit https://nikitatsym.github.io/ticktick-mcp/ to set up authorization.\n"
        "See README.md for details."
    )
