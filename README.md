# TickTick MCP Server

MCP server for [TickTick](https://ticktick.com) task manager. Create, update,
complete, and delete tasks and projects with full support for subtasks,
priorities, tags, reminders, and recurrence — from Claude, MetaMCP, or any
MCP client.

## Features

- **16 operations** covering tasks, projects, and the Inbox
- **3 risk-graded meta-tools** (`ticktick_read` / `ticktick_write` / `ticktick_delete`) — agents pick a tool surface by side-effect kind
- Pydantic param validation with `extra='forbid'` — unknown keys, missing required fields, and wrong types fail loudly
- Per-op `operation='schema'` returning a full JSON Schema; `operation='help'` with substring search (`params={'search':'X'}`)
- Brief enforcement: writes require a `<brief>summary</brief>` tag (or a `brief` parameter that injects it) so list views stay scannable
- Fail-fast on the API's silent-drop trap: `isAllDay` must be passed explicitly when changing `reminders`/`startDate`/`dueDate`
- Liveness guard on writes - UpdateTask/CompleteTask/MoveTask refuse a task that is provably in TickTick's trash (writes to trashed tasks silently vanish); completed tasks cannot be verified and pass unchecked
- Explicit timezone contract - any operation where a zone matters takes an explicit timeZone parameter; no env or system fallback
- Zero-config install via `uvx`

## Quick Start

Go to the **[setup page](https://nikitatsym.github.io/ticktick-mcp/)** — it
walks you through creating a TickTick app, authorizing, and generating the
ready-to-paste MCP config.

Works with Claude Desktop, MetaMCP, Cursor, and any MCP client that supports
stdio servers. For Claude Code global config on macOS: `~/.claude.json` →
`"mcpServers"`.

### Manual config

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "uvx",
      "args": ["--refresh", "--extra-index-url", "https://nikitatsym.github.io/ticktick-mcp/simple", "ticktick-mcp"],
      "env": {
        "TICKTICK_CLIENT_ID": "YOUR_CLIENT_ID",
        "TICKTICK_CLIENT_SECRET": "YOUR_CLIENT_SECRET",
        "TICKTICK_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/).

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `TICKTICK_CLIENT_ID` | Yes | — | OAuth client id from `developer.ticktick.com`. |
| `TICKTICK_CLIENT_SECRET` | Yes | — | OAuth client secret. |
| `TICKTICK_ACCESS_TOKEN` | Yes | — | Bearer token issued by the OAuth flow. The setup page generates this for you. |
| `MCP_TICKTICK_BRIEF_MAX` | No | `100` | Max length of the `<brief>` tag. `0` disables enforcement entirely. |

## Tool Groups

All 16 operations are exposed through 3 risk-graded meta-tools — one tool
surface per scope, dispatched via `operation` + `params`.

| Meta-tool | Scope | Operations |
|---|---|---|
| `ticktick_read` | GET, safe / read-only | `GetToday`, `GetInbox`, `GetInboxId`, `ListProjects`, `GetProject`, `GetProjectWithData`, `GetTask` |
| `ticktick_write` | Create + update | `CreateTask`, `UpdateTask`, `MoveTask`, `CompleteTask`, `CreateProject`, `UpdateProject` |
| `ticktick_delete` | Destructive | `DeleteTask`, `DeleteProject` |

`MoveTask` moves a task between projects as copy+delete (the API has no move);
the copy gets a new id, returned in the result.

`GetToday` takes a required `timeZone` - "today" is computed in that zone.

Each meta-tool takes `operation` (PascalCase op name, or `help` / `schema`)
plus a `params` dict:

```
ticktick_read(operation="help")                                                  # list every op in this group
ticktick_read(operation="help", params={"search": "today"})                      # filter by substring; surfaces cross-group hits
ticktick_read(operation="schema", params={"op": "GetTask"})                      # full JSON Schema for one op
ticktick_read(operation="GetTask", params={"projectId": "p1", "taskId": "t1"})   # invoke

ticktick_write(operation="CreateTask", params={"title": "Buy milk", "brief": "Buy milk"})
ticktick_delete(operation="DeleteTask", params={"projectId": "p1", "taskId": "t1"})
```

Params are validated strictly via Pydantic: unknown keys, wrong types, and
missing required fields return a contextual error result with field-level detail
and a pointer to `operation='schema'`.

## Important semantics

### Brief enforcement

When `MCP_TICKTICK_BRIEF_MAX > 0` (the default), every `CreateTask` /
`UpdateTask` body must carry a `<brief>one-line summary</brief>` tag. Two
equivalent ways to satisfy it:

```json
// (a) pass the brief parameter — auto-injected into content
{"title": "Q1 plan", "brief": "Outline Q1 OKRs"}

// (b) include the tag in content yourself
{"title": "Q1 plan", "content": "<brief>Outline Q1 OKRs</brief>\nFull notes…"}
```

Set `MCP_TICKTICK_BRIEF_MAX=0` to disable the requirement and the length cap.

`UpdateTask` with `brief` alone (no `content`) preserves the existing body —
the wrapper fetches the current task, rewrites only the `<brief>` tag, and
sends the rest back unchanged.

### Timezone semantics

When a task date carries a time of day (`YYYY-MM-DDTHH:MM[:SS]`) the wrapper
needs an IANA timezone to normalize it, and `GetToday` needs one to compute
day boundaries. There is exactly one source: the `timeZone` parameter of
the call. There is no environment or system fallback - a missing zone is
an error, so every applied zone is an explicit decision by the caller.
Date-only values (`YYYY-MM-DD`) are all-day and need no zone. Manual UTC
offsets (`+0300`, `Z`) are rejected - pass local time plus `timeZone`.

### `isAllDay` and reminder triggers

TickTick reminder triggers are iCal duration strings whose shape depends on
whether the task is all-day or timed:

| Task mode | Trigger shape | Example |
|---|---|---|
| All-day (`isAllDay=true`) | positive offset from midnight | `TRIGGER:PT9H` = 9am |
| Timed (`isAllDay=false`) | negative offset from event | `TRIGGER:-PT5M` = 5min before |

`UpdateTask` requires `isAllDay` to be passed **explicitly** when changing
`reminders`, `startDate`, or `dueDate` — the TickTick API silently drops
`isAllDay` if you omit it on a partial update, which causes the mode (and
therefore the reminder interpretation) to flip. The wrapper rejects the call
with an error before it reaches the API.

`CreateTask` infers `isAllDay` from the date shape: date-only
(`YYYY-MM-DD`) implies all-day; date+time implies timed. Pass `isAllDay`
explicitly to override or when there's no date.

## Development

```bash
# unit tests
npm test                     # or: uv run pytest -m 'not integration'

# lint + type-check
npm run lint                 # or: uv run ruff check . && uv run mypy src/

# integration tests — require live TICKTICK_* env vars (creates and deletes a real task)
npm run test:integration
```

`src/` is type-checked under `mypy --strict`. The two intentionally dynamic
surfaces (`server.py::_build_params_model`, `_coerce_call`) use explicit
typed escape hatches (`Any`, `Callable[..., Any]`, `cast`, `TypeAlias`); no
`# type: ignore` is allowed.

## License

[MIT](LICENSE) — [GitHub](https://github.com/nikitatsym/ticktick-mcp)
