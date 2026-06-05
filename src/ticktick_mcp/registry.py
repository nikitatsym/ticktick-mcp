"""Tool registration primitives."""

from __future__ import annotations

from typing import Any, Callable


class Group:
    """A named group of MCP tool operations exposed as a single meta-tool."""

    __slots__ = ("name", "doc")

    def __init__(self, name: str, doc: str):
        self.name = name
        self.doc = doc


ROOT = Group("root", "")


class _Unset:
    """Sentinel singleton: caller did not pass this field.

    Distinct from `None`. Optional params declared with default `_UNSET` carry
    the omitted-vs-cleared distinction through Pydantic validation
    (`exclude_unset=True`) all the way to `_prepare_task` / `_prepare_project`,
    which strip `_UNSET` as the first line so existing `is not None` checks see
    "key absent" instead of "explicit None".

    `_UNSET` is internal — must not leak into JSON Schema, `_build_help` type
    rendering, or the API payload.
    """

    _instance: "_Unset | None" = None

    def __new__(cls) -> "_Unset":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "_UNSET"

    def __bool__(self) -> bool:
        return False


_UNSET = _Unset()


def _op(group: Group) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as an MCP tool in the given group.

    A Pydantic params model is built from the signature at server registration
    time; descriptions/constraints in `Annotated[T, Field(...)]` flow into the
    JSON Schema returned by `operation='schema'`.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not fn.__doc__:
            raise RuntimeError(f"Tool function {fn.__name__!r} has no docstring")
        setattr(fn, "_mcp_group", group)
        return fn
    return decorator
