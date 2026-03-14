from importlib.metadata import version

from ticktick_mcp.server import mcp

__version__ = version("ticktick-mcp")


def main():
    mcp.run(transport="stdio")
