import io
import json
import os
import sys

from .client import TickTickClient

_log = lambda msg: print(f"[ticktick-mcp] {msg}", file=sys.stderr, flush=True)

# ── Schemas ──────────────────────────────────────────────────────────────────

_SUBTASK_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Subtask title"},
        "status": {"type": "integer", "description": "0=normal, 1=completed"},
        "startDate": {"type": "string", "description": "Subtask start date"},
        "isAllDay": {"type": "boolean", "description": "All-day subtask"},
        "sortOrder": {"type": "integer", "description": "Sort position"},
        "timeZone": {"type": "string", "description": "Time zone"},
    },
    "required": ["title"],
}

_TASK_PROPS = {
    "title": {"type": "string", "description": "Task title"},
    "projectId": {"type": "string", "description": "Project ID (uses inbox if omitted)"},
    "content": {"type": "string", "description": "Task content/notes (supports markdown)"},
    "desc": {"type": "string", "description": "Task description"},
    "startDate": {"type": "string", "description": 'Start date in ISO 8601 format, e.g. "2026-02-18T09:00:00+0000"'},
    "dueDate": {"type": "string", "description": "Due date in ISO 8601 format"},
    "isAllDay": {"type": "boolean", "description": "Whether this is an all-day task"},
    "priority": {"type": "integer", "description": "Priority: 0=none, 1=low, 3=medium, 5=high"},
    "tags": {"type": "array", "items": {"type": "string"}, "description": 'Tags as array of strings, e.g. ["work", "urgent"]'},
    "timeZone": {"type": "string", "description": 'Time zone, e.g. "America/Los_Angeles"'},
    "reminders": {"type": "array", "items": {"type": "string"}, "description": 'Reminders in iCal trigger format, e.g. ["TRIGGER:PT0S"]'},
    "repeatFlag": {"type": "string", "description": 'Recurrence rule in iCal RRULE format, e.g. "RRULE:FREQ=DAILY;INTERVAL=1"'},
    "items": {"type": "array", "items": _SUBTASK_SCHEMA, "description": "Subtask/checklist items"},
}


def _schema(properties=None, required=None):
    s = {"type": "object", "properties": properties or {}}
    if required:
        s["required"] = required
    return s


# ── Tool registry ────────────────────────────────────────────────────────────

TOOLS = {}


def tool(name, description, schema=None):
    def decorator(func):
        TOOLS[name] = {
            "description": description,
            "inputSchema": schema or _schema(),
            "handler": func,
        }
        return func
    return decorator


# ── Inbox ────────────────────────────────────────────────────────────────────

@tool("get_inbox",
    "Get the Inbox project with all its tasks. The Inbox is a special built-in project in TickTick that is NOT included in list_projects. Use this tool whenever you need to see inbox tasks. Returns the inbox project data including all tasks.")
def _get_inbox(client):
    return client.get_inbox_with_data()


@tool("get_inbox_id",
    'Get the Inbox project ID. Useful when you need the inbox projectId for other operations like complete_task, delete_task, or update_task on inbox tasks. The inbox ID has the format "inbox<userId>" and is unique per user.')
def _get_inbox_id(client):
    return {"inboxId": client.get_inbox_id()}


# ── Projects ─────────────────────────────────────────────────────────────────

@tool("list_projects",
    "List all TickTick projects (task lists). IMPORTANT: This does NOT include the Inbox — use get_inbox to access inbox tasks.")
def _list_projects(client):
    return client.list_projects()


@tool("get_project", "Get a TickTick project by ID",
    _schema({"projectId": {"type": "string", "description": "Project ID"}}, ["projectId"]))
def _get_project(client, projectId):
    return client.get_project(projectId)


@tool("get_project_with_data",
    "Get a TickTick project with all its tasks and columns. For inbox tasks, use get_inbox instead.",
    _schema({"projectId": {"type": "string", "description": "Project ID"}}, ["projectId"]))
def _get_project_with_data(client, projectId):
    return client.get_project_with_data(projectId)


@tool("create_project", "Create a new TickTick project (task list)",
    _schema({
        "name": {"type": "string", "description": "Project name"},
        "color": {"type": "string", "description": 'Color hex code, e.g. "#4772FA"'},
        "viewMode": {"type": "string", "enum": ["list", "kanban", "timeline"], "description": "View mode"},
        "kind": {"type": "string", "enum": ["TASK", "NOTE"], "description": "Project kind"},
    }, ["name"]))
def _create_project(client, **params):
    return client.create_project(params)


@tool("update_project", "Update an existing TickTick project",
    _schema({
        "projectId": {"type": "string", "description": "Project ID"},
        "name": {"type": "string", "description": "New name"},
        "color": {"type": "string", "description": "New color hex"},
        "viewMode": {"type": "string", "enum": ["list", "kanban", "timeline"], "description": "New view mode"},
        "kind": {"type": "string", "enum": ["TASK", "NOTE"], "description": "New kind"},
    }, ["projectId"]))
def _update_project(client, projectId, **updates):
    return client.update_project(projectId, updates)


@tool("delete_project", "Delete a TickTick project",
    _schema({"projectId": {"type": "string", "description": "Project ID to delete"}}, ["projectId"]))
def _delete_project(client, projectId):
    client.delete_project(projectId)
    return f"Project {projectId} deleted."


# ── Tasks ────────────────────────────────────────────────────────────────────

@tool("get_task", "Get a specific task by project ID and task ID",
    _schema({
        "projectId": {"type": "string", "description": "Project ID containing the task"},
        "taskId": {"type": "string", "description": "Task ID"},
    }, ["projectId", "taskId"]))
def _get_task(client, projectId, taskId):
    return client.get_task(projectId, taskId)


@tool("create_task",
    'Create a new task in TickTick. If projectId is omitted, the task goes to Inbox. Supports title, content, dates, priority (0=none, 1=low, 3=medium, 5=high), tags, subtasks (items), reminders, and recurrence (repeatFlag in iCal RRULE format). The response includes the assigned projectId (useful for getting the inbox ID).',
    _schema(_TASK_PROPS, ["title"]))
def _create_task(client, **params):
    return client.create_task(params)


@tool("update_task", "Update an existing task. Provide only the fields you want to change.",
    _schema({
        "taskId": {"type": "string", "description": "Task ID to update"},
        "projectId": {"type": "string", "description": "Project ID containing the task"},
        **{k: v for k, v in _TASK_PROPS.items() if k != "projectId"},
    }, ["taskId", "projectId"]))
def _update_task(client, taskId, **updates):
    return client.update_task(taskId, updates)


@tool("complete_task", "Mark a task as completed",
    _schema({
        "projectId": {"type": "string", "description": "Project ID"},
        "taskId": {"type": "string", "description": "Task ID to complete"},
    }, ["projectId", "taskId"]))
def _complete_task(client, projectId, taskId):
    client.complete_task(projectId, taskId)
    return f"Task {taskId} marked as completed."


@tool("delete_task", "Delete a task from TickTick",
    _schema({
        "projectId": {"type": "string", "description": "Project ID"},
        "taskId": {"type": "string", "description": "Task ID to delete"},
    }, ["projectId", "taskId"]))
def _delete_task(client, projectId, taskId):
    client.delete_task(projectId, taskId)
    return f"Task {taskId} deleted."


@tool("batch_create_tasks",
    "Create multiple tasks at once. Each task object supports the same fields as create_task.",
    _schema({
        "tasks": {
            "type": "array",
            "items": {"type": "object", "properties": _TASK_PROPS, "required": ["title"]},
            "description": "Array of task objects to create",
        }
    }, ["tasks"]))
def _batch_create_tasks(client, tasks):
    return client.batch_create_tasks(tasks)


# ── MCP Protocol ─────────────────────────────────────────────────────────────

def _handle(method, params, client):
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2024-11-05"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "ticktick", "version": "1.0.0"},
        }

    if method == "tools/list":
        return {
            "tools": [
                {"name": name, "description": t["description"], "inputSchema": t["inputSchema"]}
                for name, t in TOOLS.items()
            ]
        }

    if method == "tools/call":
        name = params["name"]
        args = params.get("arguments", {})
        if name not in TOOLS:
            return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}], "isError": True}
        try:
            result = TOOLS[name]["handler"](client, **args)
            text = result if isinstance(result, str) else json.dumps(result, indent=2, ensure_ascii=False)
            return {"content": [{"type": "text", "text": text}]}
        except Exception as e:
            _log(f"{name} failed: {e}")
            return {"content": [{"type": "text", "text": f"Error in {name}: {e}"}], "isError": True}

    raise ValueError(f"Method not found: {method}")


def run():
    client_id = os.environ.get("TICKTICK_CLIENT_ID")
    client_secret = os.environ.get("TICKTICK_CLIENT_SECRET")
    client = TickTickClient(client_id, client_secret)

    # Use binary streams with explicit UTF-8 encoding, no buffering on read
    stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)

    _log(f"Starting... (pid {os.getpid()})")

    while True:
        line = stdin.readline()
        if not line:
            break  # EOF
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            _log(f"Invalid JSON: {line[:120]}")
            continue

        msg_id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params", {})

        # Notifications (no id) → no response
        if msg_id is None:
            continue

        try:
            result = _handle(method, params, client)
            response = {"jsonrpc": "2.0", "id": msg_id, "result": result}
        except Exception as e:
            response = {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": str(e)}}

        stdout.write(json.dumps(response) + "\n")
        stdout.flush()
