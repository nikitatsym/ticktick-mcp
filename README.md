# TickTick MCP Server

MCP server for [TickTick](https://ticktick.com) task manager. Manage projects and tasks from Claude, MetaMCP, or any MCP client — create, complete, update, delete, batch operations, subtasks, priorities, tags, reminders, recurrence, and more.

## Setup

1. Go to the **[setup page](https://nikitatsym.github.io/ticktick-mcp/)**
2. Create a TickTick app (the page will guide you)
3. Authorize with TickTick
4. Copy the generated config into your MCP client — done!

Works with Claude Desktop, MetaMCP, and any MCP client that supports stdio servers.

### Requirements

- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)

### Manual config

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "uvx",
      "args": ["--from", "https://raw.githubusercontent.com/nikitatsym/ticktick-mcp/main/dist/ticktick_mcp-1.0.0-py3-none-any.whl", "ticktick-mcp"],
      "env": {
        "TICKTICK_CLIENT_ID": "YOUR_CLIENT_ID",
        "TICKTICK_CLIENT_SECRET": "YOUR_CLIENT_SECRET",
        "TICKTICK_ACCESS_TOKEN": "YOUR_ACCESS_TOKEN"
      }
    }
  }
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `get_inbox` | Get the Inbox with all its tasks |
| `get_inbox_id` | Get the inbox project ID |
| `list_projects` | List all projects (does not include Inbox) |
| `get_project` | Get project by ID |
| `get_project_with_data` | Get project with all tasks and columns |
| `create_project` | Create a project |
| `update_project` | Update a project |
| `delete_project` | Delete a project |
| `get_task` | Get task by project ID + task ID |
| `create_task` | Create a task (goes to Inbox if no projectId) |
| `update_task` | Update any task fields |
| `complete_task` | Mark task as done |
| `delete_task` | Delete a task |
| `batch_create_tasks` | Create multiple tasks at once |

## License

MIT — [GitHub](https://github.com/nikitatsym/ticktick-mcp)
