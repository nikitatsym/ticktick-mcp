# TickTick MCP Server

MCP server for [TickTick](https://ticktick.com) task manager. Full support for projects and tasks — create, read, update, delete, complete, batch operations, subtasks, priorities, tags, reminders, and recurrence.

## Quick Start

### 1. Register a TickTick App

1. Go to [developer.ticktick.com](https://developer.ticktick.com)
2. Click **Manage Apps** → log in → **+App Name**
3. Copy your **Client ID** and **Client Secret**
4. Set **Redirect URI** to `https://nikitatsym.github.io/ticktick-mcp/`

### 2. Authorize

Visit the setup page:

**[https://nikitatsym.github.io/ticktick-mcp/](https://nikitatsym.github.io/ticktick-mcp/)**

Enter your Client ID and Client Secret → authorize with TickTick → get a ready-to-paste JSON config.

### 3. Add to your MCP client

Paste the JSON config from the setup page into your MCP client:

#### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows).

#### MetaMCP

Add a new server with type **stdio**, paste the config.

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

## Auth Details

The server resolves tokens in this order:

1. `TICKTICK_ACCESS_TOKEN` env var → used directly (also persisted to disk for refresh)
2. `~/.ticktick-mcp/tokens.json` → loaded from disk
3. `TICKTICK_AUTH_CODE` env var → exchanged for tokens on first run (one-time, from setup page)

Token refresh happens automatically when the access token expires.

### Environment Variables

| Variable | Description |
|----------|-------------|
| `TICKTICK_CLIENT_ID` | OAuth Client ID (required) |
| `TICKTICK_CLIENT_SECRET` | OAuth Client Secret (required) |
| `TICKTICK_ACCESS_TOKEN` | Access token (set by setup page or manually) |
| `TICKTICK_REFRESH_TOKEN` | Refresh token (for auto-renewal) |
| `TICKTICK_AUTH_CODE` | One-time auth code (fallback if setup page can't exchange tokens) |

## License

MIT
