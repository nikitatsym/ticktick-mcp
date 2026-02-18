# TickTick MCP Server

MCP server for [TickTick](https://ticktick.com) task manager. Full support for projects and tasks — create, read, update, delete, complete, batch operations, subtasks, priorities, tags, reminders, and recurrence.

## Setup

### 1. Register a TickTick App

1. Go to [developer.ticktick.com](https://developer.ticktick.com)
2. Click **Manage Apps** → log in → **+App Name**
3. Copy your **Client ID** and **Client Secret**
4. Set **Redirect URI** to `http://localhost:8585/callback`

### 2. Install

```bash
git clone <this-repo>
cd ticktick-mcp
npm install
```

### 3. Authorize

#### Option A: Local machine (automatic)

The server will open a browser for OAuth on first launch. Just add the config and start using it.

#### Option B: Remote server / MetaMCP

Run the auth helper **on your local machine** (where you have a browser):

```bash
TICKTICK_CLIENT_ID=xxx TICKTICK_CLIENT_SECRET=yyy node src/auth.js
```

It will open the browser, authorize, and print the tokens. Copy them to your server config.

## MCP Config

### Claude Desktop / MetaMCP (local)

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "node",
      "args": ["/absolute/path/to/ticktick-mcp/src/index.js"],
      "env": {
        "TICKTICK_CLIENT_ID": "your_client_id",
        "TICKTICK_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

### Remote server (with pre-obtained tokens)

```json
{
  "mcpServers": {
    "ticktick": {
      "command": "node",
      "args": ["/absolute/path/to/ticktick-mcp/src/index.js"],
      "env": {
        "TICKTICK_CLIENT_ID": "your_client_id",
        "TICKTICK_CLIENT_SECRET": "your_client_secret",
        "TICKTICK_ACCESS_TOKEN": "token_from_auth_helper",
        "TICKTICK_REFRESH_TOKEN": "refresh_token_from_auth_helper"
      }
    }
  }
}
```

## Available Tools

### Inbox

| Tool | Description |
|------|-------------|
| `get_inbox` | Get the Inbox with all its tasks (Inbox is NOT in `list_projects`) |
| `get_inbox_id` | Get the inbox project ID (format: `inbox<userId>`) |

### Projects

| Tool | Description |
|------|-------------|
| `list_projects` | List all projects (does NOT include Inbox) |
| `get_project` | Get project by ID |
| `get_project_with_data` | Get project with all tasks and columns |
| `create_project` | Create a project (name, color, viewMode, kind) |
| `update_project` | Update a project |
| `delete_project` | Delete a project |

### Tasks

| Tool | Description |
|------|-------------|
| `get_task` | Get task by project ID + task ID |
| `create_task` | Create a task (goes to Inbox if no projectId) |
| `update_task` | Update any task fields |
| `complete_task` | Mark task as done |
| `delete_task` | Delete a task |
| `batch_create_tasks` | Create multiple tasks at once |

### Task Fields

- **title** — task title
- **projectId** — target project (inbox if omitted)
- **content** — notes/content (markdown)
- **priority** — `0` none, `1` low, `3` medium, `5` high
- **tags** — `["work", "urgent"]`
- **startDate / dueDate** — ISO 8601 (`2026-02-18T09:00:00+0000`)
- **isAllDay** — all-day task flag
- **reminders** — iCal triggers (`["TRIGGER:PT0S"]`)
- **repeatFlag** — iCal RRULE (`"RRULE:FREQ=DAILY;INTERVAL=1"`)
- **items** — subtasks/checklist items

## Auth Priority

1. `TICKTICK_ACCESS_TOKEN` env var → used immediately
2. `~/.ticktick-mcp/tokens.json` → loaded from disk
3. Nothing found → interactive OAuth flow (opens browser)

Token refresh happens automatically when the access token expires.

## License

MIT
