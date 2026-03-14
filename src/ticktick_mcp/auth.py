import os

REDIRECT_URI = "https://nikitatsym.github.io/ticktick-mcp/"
SCOPES = "tasks:read tasks:write"


def get_access_token():
    token = os.environ.get("TICKTICK_ACCESS_TOKEN")
    if token:
        return token
    raise Exception(
        "No authentication token found.\n"
        "Set TICKTICK_ACCESS_TOKEN environment variable.\n"
        "Visit https://nikitatsym.github.io/ticktick-mcp/ to set up authorization.\n"
        "See README.md for details."
    )
