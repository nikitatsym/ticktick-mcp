from importlib.metadata import version

from ticktick_mcp.server import mcp

__version__ = version("ticktick-mcp")


def main() -> None:
    mcp.run(transport="stdio")
