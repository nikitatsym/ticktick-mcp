"""TickTick MCP server — auto-discovery, grouping, and dispatch."""

import inspect
import json
import typing

from mcp.server.fastmcp import FastMCP

from . import tools as _tools_module

mcp = FastMCP("ticktick")


# ── Group meta-tool docs ─────────────────────────────────────────────────────

_GROUP_DOCS: dict[str, str] = {
    "ticktick_read": (
        "Query TickTick data (safe, read-only).\n\n"
        "Call with operation=\"help\" to list all available read operations.\n"
        "Otherwise pass the operation name and a JSON object with parameters.\n\n"
        "Example: ticktick_read(operation=\"GetTask\", "
        "params='{\"projectId\": \"abc\", \"taskId\": \"xyz\"}')"
    ),
    "ticktick_write": (
        "Create, update, or complete TickTick resources (non-destructive).\n\n"
        "Call with operation=\"help\" to list all available write operations.\n"
        "Otherwise pass the operation name and a JSON object with parameters.\n\n"
        "Example: ticktick_write(operation=\"CreateTask\", "
        "params='{\"title\": \"Buy milk\"}')"
    ),
    "ticktick_delete": (
        "Delete TickTick resources (destructive, irreversible).\n\n"
        "Call with operation=\"help\" to list all available delete operations.\n"
        "Otherwise pass the operation name and a JSON object with parameters.\n\n"
        "Example: ticktick_delete(operation=\"DeleteTask\", "
        "params='{\"projectId\": \"abc\", \"taskId\": \"xyz\"}')"
    ),
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _to_pascal(name: str) -> str:
    """get_today → GetToday"""
    return "".join(w.capitalize() for w in name.split("_"))


def _parse_bool(val, default: bool) -> bool:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes")
    return bool(val)


def _is_bool_hint(hint) -> bool:
    """Check if a type hint is bool or Optional[bool]."""
    if hint is bool:
        return True
    args = typing.get_args(hint)
    return bool in args if args else False


def _coerce_call(fn, params: dict) -> str:
    """Coerce JSON-parsed params to match function signature, then call fn."""
    sig = inspect.signature(fn)
    hints = typing.get_type_hints(fn)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name not in params:
            continue
        val = params[name]
        hint = hints.get(name)
        if hint and _is_bool_hint(hint) and not isinstance(val, bool):
            default = param.default
            if default is inspect.Parameter.empty or default is None:
                default = False
            val = _parse_bool(val, default)
        kwargs[name] = val
    return fn(**kwargs)


# ── Module-level state (populated by _register_tools) ────────────────────────

_group_ops: dict[str, dict] = {}    # {group_name: {PascalName: fn}}
_all_grouped: dict[str, str] = {}   # {PascalName: group_name}


def _build_help(group_name: str) -> str:
    """Build help text from operation functions in a group."""
    ops = _group_ops[group_name]
    lines = []
    for pascal_name, fn in ops.items():
        sig = inspect.signature(fn)
        params = ", ".join(sig.parameters.keys())
        lines.append(f"  {pascal_name}({params}) — {fn._mcp_desc}")
    return f"{len(lines)} operations available:\n" + "\n".join(lines)


def _dispatch(operation: str, group_name: str, params_str: str) -> str:
    """Dispatch an operation call to the right function."""
    ops = _group_ops[group_name]
    if operation not in ops:
        if operation in _all_grouped:
            correct = _all_grouped[operation]
            return json.dumps({
                "error": f"{operation} belongs to {correct}. Use {correct}() instead."
            })
        return json.dumps({
            "error": f"Unknown operation: {operation}. "
                     "Use operation=\"help\" to list available operations."
        })

    fn = ops[operation]
    params = json.loads(params_str) if params_str and params_str.strip() else {}
    return _coerce_call(fn, params)


# ── Registration ─────────────────────────────────────────────────────────────


def _register_tools():
    """Discover @_op-decorated functions, validate, and register as MCP tools."""
    groups: dict[str, dict[str, object]] = {}  # {group: {snake_name: fn}}

    for name, fn in inspect.getmembers(_tools_module, inspect.isfunction):
        if not hasattr(fn, "_mcp_group"):
            continue
        group = fn._mcp_group
        if not hasattr(fn, "_mcp_desc"):
            raise RuntimeError(f"@_op on {name!r} is missing desc=")
        if group == "root":
            fn.__doc__ = fn._mcp_desc
            mcp.tool()(fn)
        else:
            if group not in _GROUP_DOCS:
                raise RuntimeError(
                    f"Function {name!r} has group {group!r} "
                    "but _GROUP_DOCS is missing it"
                )
            groups.setdefault(group, {})[name] = fn

    # Build operation maps and register meta-tools
    for group_name, fns in groups.items():
        ops = {_to_pascal(n): fn for n, fn in fns.items()}
        _group_ops[group_name] = ops
        for pascal_name in ops:
            _all_grouped[pascal_name] = group_name

        def _make_tool(gname):
            def tool_fn(operation: str, params: str = "{}") -> str:
                if operation == "help":
                    return _build_help(gname)
                return _dispatch(operation, gname, params)
            tool_fn.__name__ = gname
            tool_fn.__qualname__ = gname
            tool_fn.__doc__ = _GROUP_DOCS[gname]
            return tool_fn

        mcp.tool()(_make_tool(group_name))


_register_tools()
