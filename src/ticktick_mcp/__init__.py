import sys

from ticktick_mcp.server import mcp


def main():
    print("[ticktick-mcp] starting", file=sys.stderr, flush=True)
    mcp.run(transport="stdio")
    print("[ticktick-mcp] exited", file=sys.stderr, flush=True)
