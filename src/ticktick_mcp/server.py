"""TickTick MCP server — auto-discovery, Pydantic validation, schema introspection, dispatch.

Behavior ported from gitea-mcp/server.py. Two surfaces here are inherently
dynamic — `_build_params_model` synthesises Pydantic models from arbitrary
tool signatures, and `_coerce_call` dispatches into those models. Their
dynamism is expressed through explicit, localized escape hatches (`Any`,
`Callable[..., Any]`, `type[BaseModel]`, `cast`) so the rest of the file
stays mypy-strict clean.
"""

from __future__ import annotations

import inspect
import types
import typing
from typing import Any, Callable, TypeAlias, cast

from mcp.server.fastmcp import FastMCP
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    create_model,
    field_validator,
)
from pydantic_core import PydanticUndefined

from . import tools as _tools_module
from .config import get_settings
from .registry import _UNSET, ROOT, Group, _Unset

ToolFn: TypeAlias = Callable[..., Any]
ParamsModel: TypeAlias = type[BaseModel]

mcp = FastMCP("ticktick")


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_pascal(name: str) -> str:
    """get_today → GetToday"""
    return "".join(w.capitalize() for w in name.split("_"))


def _build_params_model(fn: ToolFn) -> ParamsModel:
    """Build a Pydantic model from a function's signature.

    Parameters without a default become required fields. Defaults of `_UNSET`
    are stored as `Field(default_factory=lambda: _UNSET)` so the sentinel
    materializes only at validation time; combined with
    `model_dump(exclude_unset=True)` in `_coerce_call`, the omitted state
    flows through unchanged to the tool body. `extra='forbid'` rejects
    unknown keys with a field-level error.
    """
    hints = typing.get_type_hints(fn, include_extras=True)
    sig = inspect.signature(fn)
    fields: dict[str, Any] = {}
    for name, param in sig.parameters.items():
        ann = hints.get(name, Any)
        if param.default is inspect.Parameter.empty:
            fields[name] = (ann, ...)
        elif isinstance(param.default, _Unset):
            fields[name] = (ann, Field(default_factory=lambda: _UNSET))
        else:
            fields[name] = (ann, param.default)

    @field_validator("*", mode="before")
    def _coerce_string_bool(cls: type[BaseModel], v: Any, info: Any) -> Any:
        if not isinstance(v, str):
            return v
        ann = cls.model_fields[info.field_name].annotation
        types_in_ann = (ann,) + typing.get_args(ann)
        if bool not in types_in_ann:
            return v
        lower = v.lower()
        if lower in ("true", "1", "yes"):
            return True
        if lower in ("false", "0", "no"):
            return False
        return v

    return cast(ParamsModel, create_model(
        f"{_to_pascal(fn.__name__)}Params",
        __config__=ConfigDict(extra="forbid"),
        __validators__={"_coerce_string_bool": _coerce_string_bool},
        **fields,
    ))


def _format_validation_error(err: ValidationError, op_name: str) -> str:
    """Pydantic ValidationError → readable multi-line message."""
    lines = [f"Invalid params for {op_name}:"]
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"]) or "<root>"
        msg = e["msg"]
        got = repr(e.get("input"))
        if len(got) > 80:
            got = got[:77] + "..."
        lines.append(f"  - {loc}: {msg} (got {got})")
    lines.append(
        f"Call operation='schema', params={{'op': {op_name!r}}} for full parameter spec."
    )
    return "\n".join(lines)


def _coerce_call(fn: ToolFn, params: dict[str, Any], op_name: str) -> Any:
    """Validate params via the tool's Pydantic model, then call fn."""
    model: ParamsModel = getattr(fn, "_params_model")
    try:
        validated = model.model_validate(params)
    except ValidationError as e:
        raise ValueError(_format_validation_error(e, op_name)) from e
    return fn(**validated.model_dump(exclude_unset=True))


# ── Type rendering for help text ─────────────────────────────────────────────


def _type_to_str(hint: Any) -> str:
    """Compact human-readable rendering of a type hint for help text."""
    if hint is type(None):
        return "None"
    if hint is Any:
        return "any"
    origin = typing.get_origin(hint)
    args = typing.get_args(hint)
    if origin is typing.Literal:
        return "|".join(repr(a) for a in args)
    if origin is typing.Union or isinstance(hint, types.UnionType):
        non_none = [a for a in args if a is not type(None)]
        return "|".join(_type_to_str(a) for a in non_none) or "any"
    if origin is list:
        return f"list[{_type_to_str(args[0])}]" if args else "list"
    if origin is dict:
        if len(args) == 2:
            return f"dict[{_type_to_str(args[0])},{_type_to_str(args[1])}]"
        return "dict"
    if origin is tuple:
        return f"tuple[{','.join(_type_to_str(a) for a in args)}]" if args else "tuple"
    if hasattr(hint, "__name__"):
        return cast(str, hint.__name__)
    return str(hint).replace("typing.", "")


def _format_param_for_help(name: str, field: Any) -> str:
    """Render one parameter line: `name: type` (required) or `name?: type[=default]`.

    Factory-defaulted fields — including `_UNSET` — render as `name?: type`
    with no `=…` suffix. Without this guard, Pydantic's `PydanticUndefined`
    would leak into help, which is a real discovery bug for agents.
    """
    type_str = _type_to_str(field.annotation)
    if field.is_required():
        return f"{name}: {type_str}"
    if field.default_factory is not None or field.default is PydanticUndefined:
        return f"{name}?: {type_str}"
    if field.default is None:
        return f"{name}?: {type_str}"
    return f"{name}?: {type_str}={field.default!r}"


# ── Module-level state (populated by _register_tools) ────────────────────────

_group_ops: dict[str, dict[str, ToolFn]] = {}
_all_grouped: dict[str, str] = {}


def _render_ops_block(ops: dict[str, ToolFn]) -> str:
    """Render the per-op signature block: signature line + indented body +
    per-param `name: description` bullets for every Pydantic field whose
    `Field(description=...)` is set.
    """
    lines: list[str] = []
    for pascal_name, fn in ops.items():
        model: ParamsModel = getattr(fn, "_params_model")
        parts = [
            _format_param_for_help(n, f)
            for n, f in model.model_fields.items()
        ]
        doc = inspect.getdoc(fn) or ""
        head, _, body = doc.partition("\n\n")
        head = " ".join(head.split())
        lines.append(f"  {pascal_name}({', '.join(parts)}) — {head}")
        for body_line in body.rstrip().splitlines():
            lines.append(f"    {body_line}" if body_line else "")
        for name, field in model.model_fields.items():
            if field.description:
                lines.append(f"    {name}: {field.description}")
    return "\n".join(lines)


def _write_group_banner() -> str:
    """One-line banner for ticktick_write help: current MCP_TICKTICK_TIMEZONE
    fallback value. Lets the agent learn the silent default before its first
    write — closes the timezone-fallback failure mode.
    """
    tz = get_settings().mcp_ticktick_timezone
    if tz:
        return (
            f"Timezone fallback (MCP_TICKTICK_TIMEZONE): {tz!r}. "
            "Used when startDate/dueDate has a time and no timeZone param is passed. "
            "The zone actually used is echoed back as _used_timezone in write results."
        )
    return (
        "Timezone fallback (MCP_TICKTICK_TIMEZONE): (unset — timeZone parameter is "
        "required when startDate/dueDate has a time)."
    )


def _build_help(group_name: str, search: str | None = None) -> str:
    """Per-op signature with types, docstring body, and per-param description bullets."""
    ops = _group_ops[group_name]
    header_suffix = (
        " Call operation='schema', params={'op': 'OpName'} for the full JSON Schema."
    )

    banner = _write_group_banner() + "\n" if group_name == "ticktick_write" else ""

    if search:
        s = search.lower()

        def _hit(name: str, fn: ToolFn) -> bool:
            return (
                s in name.lower()
                or s in fn.__name__.lower()
                or s in (inspect.getdoc(fn) or "").lower()
            )

        matched = {pn: fn for pn, fn in ops.items() if _hit(pn, fn)}
        elsewhere: dict[str, list[str]] = {}
        for op_name, other_group in _all_grouped.items():
            if other_group == group_name:
                continue
            if _hit(op_name, _group_ops[other_group][op_name]):
                elsewhere.setdefault(other_group, []).append(op_name)
        if not matched:
            msg = f"No ops in {group_name} matching {search!r}."
            if elsewhere:
                msg += " Found in other groups: " + "; ".join(
                    f"{g}: {', '.join(sorted(names))}"
                    for g, names in sorted(elsewhere.items())
                )
            else:
                msg += " Call operation='help' (no params) to list all ops."
            return msg
        header = (
            f"{len(matched)} of {len(ops)} operations in {group_name} "
            f"matching {search!r}.{header_suffix}"
        )
        body = _render_ops_block(matched)
        if elsewhere:
            body += "\n\nAlso matching in other groups: " + "; ".join(
                f"{g}: {', '.join(sorted(names))}"
                for g, names in sorted(elsewhere.items())
            )
        return f"{banner}{header}\n{body}"

    header = f"{len(ops)} operations available.{header_suffix}"
    return f"{banner}{header}\n{_render_ops_block(ops)}"


def _build_schema(group_name: str, op_name: str | None) -> dict[str, Any]:
    """JSON Schema for one op (params={'op': 'X'}) or list of op names (params={})."""
    ops = _group_ops[group_name]
    if op_name is None:
        return {
            "operations": sorted(ops.keys()),
            "hint": "Pass params={'op': '<OpName>'} to get the full JSON Schema.",
        }
    if op_name not in ops:
        raise ValueError(
            f"Unknown operation {op_name!r} in {group_name}. "
            f"Available: {sorted(ops)}"
        )
    fn = ops[op_name]
    model: ParamsModel = getattr(fn, "_params_model")
    schema: dict[str, Any] = model.model_json_schema()
    doc = inspect.getdoc(fn) or ""
    if doc:
        schema["description"] = doc
    return schema


def _dispatch(operation: str, group_name: str, params: dict[str, Any]) -> Any:
    """Route an operation call. Fails loud (ValueError) on anything wrong."""
    if operation == "schema":
        return _build_schema(group_name, params.get("op"))
    ops = _group_ops[group_name]
    if operation not in ops:
        if operation in _all_grouped:
            correct = _all_grouped[operation]
            raise ValueError(
                f"{operation!r} belongs to {correct!r}, not {group_name!r}. "
                f"Call {correct}(operation={operation!r}, ...) instead."
            )
        raise ValueError(
            f"Unknown operation {operation!r} in {group_name}. "
            "Use operation='help' to list or operation='schema' for details."
        )
    return _coerce_call(ops[operation], params, operation)


# ── Registration ─────────────────────────────────────────────────────────────


def _register_tools() -> None:
    """Discover @_op-decorated functions, build Pydantic models, register MCP tools."""
    groups: dict[str, tuple[Group, dict[str, ToolFn]]] = {}

    for name, fn in inspect.getmembers(_tools_module, inspect.isfunction):
        group = getattr(fn, "_mcp_group", None)
        if group is None:
            continue
        setattr(fn, "_params_model", _build_params_model(fn))
        if group is ROOT:
            mcp.tool()(fn)
        else:
            if group.name not in groups:
                groups[group.name] = (group, {})
            groups[group.name][1][name] = fn

    for group_name, (group, fns) in groups.items():
        ops = {_to_pascal(n): fn for n, fn in fns.items()}
        _group_ops[group_name] = ops
        for pascal_name in ops:
            _all_grouped[pascal_name] = group_name

        def _make_tool(gname: str, gdoc: str) -> ToolFn:
            def tool_fn(operation: str, params: dict[str, Any] | None = None) -> Any:
                params = params or {}
                if operation == "help":
                    return _build_help(gname, search=params.get("search"))
                return _dispatch(operation, gname, params)
            tool_fn.__name__ = gname
            tool_fn.__qualname__ = gname
            tool_fn.__doc__ = gdoc
            return tool_fn

        mcp.tool()(_make_tool(group_name, group.doc))


_register_tools()
