"""Tool registration primitives."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, cast

from typing_extensions import Self


class Group:
    """A named group of MCP tool operations exposed as a single meta-tool."""

    __slots__ = ("doc", "name")

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

    _instance: _Unset | None = None

    def __new__(cls) -> Self:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        # _instance is typed _Unset (the base, non-generic slot) - Self here
        # is always exactly _Unset since nothing subclasses this sentinel.
        return cast(Self, cls._instance)

    def __repr__(self) -> str:
        return "_UNSET"

    def __bool__(self) -> bool:
        return False


_UNSET = _Unset()


# Dispatch metadata used to be read/written with literal getattr/setattr, which
# ruff 0.16 bans (B009/B010); plain attribute access needs a static shape
# instead. Split in two because `_mcp_group` is attached by `_op` at import
# time while `_params_model` only exists after `server._register_tools` runs.
class TaggedFn(Protocol):
    """Tool function after `_op`: carries only the group tag."""

    __name__: str
    _mcp_group: Group

    def __call__(self, *args: Any, **kwargs: Any) -> Any: ...


class OpFn(TaggedFn, Protocol):
    """Tool function after `server._register_tools`: full dispatch metadata."""

    _params_model: type[Any]


def _op(group: Group) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Mark a function as an MCP tool in the given group.

    A Pydantic params model is built from the signature at server registration
    time; descriptions/constraints in `Annotated[T, Field(...)]` flow into the
    JSON Schema returned by `operation='schema'`.
    """
    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        if not fn.__doc__:
            raise RuntimeError(f"Tool function {fn.__name__!r} has no docstring")
        cast(TaggedFn, fn)._mcp_group = group
        return fn
    return decorator
