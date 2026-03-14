"""TickTick MCP server — auto-discovery, grouping, and dispatch."""

import inspect
import json
import typing

from mcp.server.fastmcp import FastMCP

from . import tools as _tools_module

mcp = FastMCP("ticktick")


# ── Grouping ─────────────────────────────────────────────────────────────────
# The single source of truth for how operations are exposed as MCP tools.
# Grouped operations → dispatched via meta-tools (ticktick_read, etc.).
# Ungrouped operations → registered as individual MCP tools.

_GROUPS: dict[str, list[str]] = {
    "ticktick_read": [
        "get_today", "get_inbox", "get_inbox_id", "list_projects",
        "get_project", "get_project_with_data", "get_task",
    ],
    "ticktick_write": [
        "create_task", "update_task", "complete_task",
        "create_project", "update_project",
    ],
    "ticktick_delete": [
        "delete_task", "delete_project",
    ],
}

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
        doc = fn.__doc__.split("\n")[0]
        lines.append(f"  {pascal_name}({params}) — {doc}")
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
    """Discover tool functions, validate, and register as MCP tools."""
    # Collect all public functions defined in tools module
    all_ops = {}
    for name, fn in inspect.getmembers(_tools_module, inspect.isfunction):
        if name.startswith("_"):
            continue
        if fn.__module__ != _tools_module.__name__:
            continue
        if not fn.__doc__:
            raise RuntimeError(f"Tool function {name!r} in tools.py has no docstring")
        all_ops[name] = fn

    # Validate groups reference existing functions
    grouped = set()
    for group_name, fn_names in _GROUPS.items():
        if group_name not in _GROUP_DOCS:
            raise RuntimeError(f"_GROUPS has {group_name!r} but _GROUP_DOCS is missing it")
        for fn_name in fn_names:
            if fn_name not in all_ops:
                raise RuntimeError(
                    f"_GROUPS[{group_name!r}] references {fn_name!r} "
                    "but no such public function exists in tools.py"
                )
            grouped.add(fn_name)

    # Build operation maps
    for group_name, fn_names in _GROUPS.items():
        ops = {_to_pascal(n): all_ops[n] for n in fn_names}
        _group_ops[group_name] = ops
        for pascal_name in ops:
            _all_grouped[pascal_name] = group_name

    # Register grouped operations as meta-tools
    for group_name in _GROUPS:
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

    # Register ungrouped functions as individual MCP tools
    for name, fn in all_ops.items():
        if name not in grouped:
            mcp.tool()(fn)


_register_tools()
