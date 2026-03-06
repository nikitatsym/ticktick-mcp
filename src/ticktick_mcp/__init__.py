import os

if os.environ.get("TICKTICK_COMPACT", "").lower() in ("1", "true", "yes"):
    from ticktick_mcp.server_compact import mcp
else:
    from ticktick_mcp.server import mcp


def main():
    mcp.run(transport="stdio")
