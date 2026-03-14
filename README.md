# TickTick MCP Server

MCP server for [TickTick](https://ticktick.com) task manager. Manage projects and tasks from Claude, MetaMCP, or any MCP client — create, complete, update, delete, subtasks, priorities, tags, reminders, recurrence, and more.

## Setup

1. Go to the **[setup page](https://nikitatsym.github.io/ticktick-mcp/)**
2. Create a TickTick app (the page will guide you)
3. Authorize with TickTick
4. Copy the generated config into your MCP client — done!

Works with Claude Desktop, MetaMCP, and any MCP client that supports stdio servers.
For Claude Code global config on macOS: `~/.claude.json` → `"mcpServers"`.

### Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

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
        "TICKTICK_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN",
        "TICKTICK_DESC_DEFAULT": "false",
        "TICKTICK_DESC_COMPACT_DEFAULT": "true"
      }
    }
  }
}
```

### Optional env vars

| Variable | Default | Description |
|----------|---------|-------------|
| `TICKTICK_DESC_DEFAULT` | `false` | Include task descriptions in list responses |
| `TICKTICK_DESC_COMPACT_DEFAULT` | `true` | When descriptions are included, return only `<brief>...</brief>` content |
| `TICKTICK_SLIM_DEFAULT` | `true` | Strip verbose fields from task listings |
| `TICKTICK_REQUIRE_BRIEF` | `true` | Require `<brief>summary</brief>` tag in task content on create/edit |
| `TICKTICK_BRIEF_MAX_LENGTH` | `200` | Max character length for brief summary |
## Tools

The server exposes 3 meta-tools with operation-based dispatch. Use `operation="help"` to list available operations.

| Meta-tool | Ops | Description |
|-----------|-----|-------------|
| `ticktick_read` | 7 | GetToday, GetInbox, GetInboxId, ListProjects, GetProject, GetProjectWithData, GetTask |
| `ticktick_write` | 5 | CreateTask, UpdateTask, CompleteTask, CreateProject, UpdateProject |
| `ticktick_delete` | 2 | DeleteTask, DeleteProject |

Each tool takes `(operation, params)` where `params` is a JSON string.

## License

MIT — [GitHub](https://github.com/nikitatsym/ticktick-mcp)
