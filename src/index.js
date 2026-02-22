#!/usr/bin/env node

import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { TickTickClient } from './ticktick-client.js';

const log = (...args) => console.error('[ticktick-mcp]', ...args);

// Catch uncaught errors — write to stderr only (stdout = MCP protocol)
process.on('uncaughtException', (err) => {
  log('Uncaught exception:', err);
});
process.on('unhandledRejection', (reason) => {
  log('Unhandled rejection:', reason);
});

const clientId = process.env.TICKTICK_CLIENT_ID;
const clientSecret = process.env.TICKTICK_CLIENT_SECRET;

const client = new TickTickClient(null, clientId, clientSecret);

const server = new McpServer(
  { name: 'ticktick', version: '1.0.0' },
  { capabilities: { logging: {} } },
);

/**
 * Wrap a tool handler with error handling.
 * On error: logs to stderr, sends MCP log notification, returns { isError: true }.
 */
function withErrorHandling(toolName, handler) {
  return async (...args) => {
    try {
      return await handler(...args);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      log(`${toolName} failed:`, message);
      try {
        server.server.sendLoggingMessage({
          level: 'error',
          logger: toolName,
          data: message,
        });
      } catch {
        // server might not be connected yet
      }
      return {
        isError: true,
        content: [{ type: 'text', text: `Error in ${toolName}: ${message}` }],
      };
    }
  };
}

// ─── Inbox ──────────────────────────────────────────────────────────────────

server.tool(
  'get_inbox',
  'Get the Inbox project with all its tasks. The Inbox is a special built-in project in TickTick that is NOT included in list_projects. Use this tool whenever you need to see inbox tasks. Returns the inbox project data including all tasks.',
  {},
  withErrorHandling('get_inbox', async () => {
    const data = await client.getInboxWithData();
    return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
  })
);

server.tool(
  'get_inbox_id',
  'Get the Inbox project ID. Useful when you need the inbox projectId for other operations like complete_task, delete_task, or update_task on inbox tasks. The inbox ID has the format "inbox<userId>" and is unique per user.',
  {},
  withErrorHandling('get_inbox_id', async () => {
    const inboxId = await client.getInboxId();
    return { content: [{ type: 'text', text: JSON.stringify({ inboxId }, null, 2) }] };
  })
);

// ─── Projects ───────────────────────────────────────────────────────────────

server.tool(
  'list_projects',
  'List all TickTick projects (task lists). IMPORTANT: This does NOT include the Inbox — use get_inbox to access inbox tasks.',
  {},
  withErrorHandling('list_projects', async () => {
    const projects = await client.listProjects();
    return { content: [{ type: 'text', text: JSON.stringify(projects, null, 2) }] };
  })
);

server.tool(
  'get_project',
  'Get a TickTick project by ID',
  { projectId: z.string().describe('Project ID') },
  withErrorHandling('get_project', async ({ projectId }) => {
    const project = await client.getProject(projectId);
    return { content: [{ type: 'text', text: JSON.stringify(project, null, 2) }] };
  })
);

server.tool(
  'get_project_with_data',
  'Get a TickTick project with all its tasks and columns. For inbox tasks, use get_inbox instead.',
  { projectId: z.string().describe('Project ID') },
  withErrorHandling('get_project_with_data', async ({ projectId }) => {
    const data = await client.getProjectWithData(projectId);
    return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
  })
);

server.tool(
  'create_project',
  'Create a new TickTick project (task list)',
  {
    name: z.string().describe('Project name'),
    color: z.string().optional().describe('Color hex code, e.g. "#4772FA"'),
    viewMode: z.enum(['list', 'kanban', 'timeline']).optional().describe('View mode'),
    kind: z.enum(['TASK', 'NOTE']).optional().describe('Project kind'),
  },
  withErrorHandling('create_project', async (params) => {
    const project = await client.createProject(params);
    return { content: [{ type: 'text', text: JSON.stringify(project, null, 2) }] };
  })
);

server.tool(
  'update_project',
  'Update an existing TickTick project',
  {
    projectId: z.string().describe('Project ID'),
    name: z.string().optional().describe('New name'),
    color: z.string().optional().describe('New color hex'),
    viewMode: z.enum(['list', 'kanban', 'timeline']).optional().describe('New view mode'),
    kind: z.enum(['TASK', 'NOTE']).optional().describe('New kind'),
  },
  withErrorHandling('update_project', async ({ projectId, ...updates }) => {
    const project = await client.updateProject(projectId, updates);
    return { content: [{ type: 'text', text: JSON.stringify(project, null, 2) }] };
  })
);

server.tool(
  'delete_project',
  'Delete a TickTick project',
  { projectId: z.string().describe('Project ID to delete') },
  withErrorHandling('delete_project', async ({ projectId }) => {
    await client.deleteProject(projectId);
    return { content: [{ type: 'text', text: `Project ${projectId} deleted.` }] };
  })
);

// ─── Tasks ──────────────────────────────────────────────────────────────────

server.tool(
  'get_task',
  'Get a specific task by project ID and task ID',
  {
    projectId: z.string().describe('Project ID containing the task'),
    taskId: z.string().describe('Task ID'),
  },
  withErrorHandling('get_task', async ({ projectId, taskId }) => {
    const task = await client.getTask(projectId, taskId);
    return { content: [{ type: 'text', text: JSON.stringify(task, null, 2) }] };
  })
);

server.tool(
  'create_task',
  'Create a new task in TickTick. If projectId is omitted, the task goes to Inbox. Supports title, content, dates, priority (0=none, 1=low, 3=medium, 5=high), tags, subtasks (items), reminders, and recurrence (repeatFlag in iCal RRULE format). The response includes the assigned projectId (useful for getting the inbox ID).',
  {
    title: z.string().describe('Task title'),
    projectId: z.string().optional().describe('Project ID (uses inbox if omitted)'),
    content: z.string().optional().describe('Task content/notes (supports markdown)'),
    desc: z.string().optional().describe('Task description'),
    startDate: z.string().optional().describe('Start date in ISO 8601 format, e.g. "2026-02-18T09:00:00+0000"'),
    dueDate: z.string().optional().describe('Due date in ISO 8601 format'),
    isAllDay: z.boolean().optional().describe('Whether this is an all-day task'),
    priority: z.number().optional().describe('Priority: 0=none, 1=low, 3=medium, 5=high'),
    tags: z.array(z.string()).optional().describe('Tags as array of strings, e.g. ["work", "urgent"]'),
    timeZone: z.string().optional().describe('Time zone, e.g. "America/Los_Angeles"'),
    reminders: z.array(z.string()).optional().describe('Reminders in iCal trigger format, e.g. ["TRIGGER:PT0S", "TRIGGER:P0DT9H0M0S"]'),
    repeatFlag: z.string().optional().describe('Recurrence rule in iCal RRULE format, e.g. "RRULE:FREQ=DAILY;INTERVAL=1"'),
    items: z
      .array(
        z.object({
          title: z.string().describe('Subtask title'),
          status: z.number().optional().describe('0=normal, 1=completed'),
          startDate: z.string().optional().describe('Subtask start date'),
          isAllDay: z.boolean().optional().describe('All-day subtask'),
          sortOrder: z.number().optional().describe('Sort position'),
          timeZone: z.string().optional().describe('Time zone'),
        })
      )
      .optional()
      .describe('Subtask/checklist items'),
  },
  withErrorHandling('create_task', async (params) => {
    const task = await client.createTask(params);
    return { content: [{ type: 'text', text: JSON.stringify(task, null, 2) }] };
  })
);

server.tool(
  'update_task',
  'Update an existing task. Provide only the fields you want to change.',
  {
    taskId: z.string().describe('Task ID to update'),
    projectId: z.string().describe('Project ID containing the task'),
    title: z.string().optional().describe('New title'),
    content: z.string().optional().describe('New content/notes'),
    desc: z.string().optional().describe('New description'),
    startDate: z.string().optional().describe('New start date (ISO 8601)'),
    dueDate: z.string().optional().describe('New due date (ISO 8601)'),
    isAllDay: z.boolean().optional().describe('All-day flag'),
    priority: z.number().optional().describe('Priority: 0=none, 1=low, 3=medium, 5=high'),
    tags: z.array(z.string()).optional().describe('New tags'),
    timeZone: z.string().optional().describe('Time zone'),
    reminders: z.array(z.string()).optional().describe('New reminders'),
    repeatFlag: z.string().optional().describe('New recurrence rule'),
    items: z
      .array(
        z.object({
          title: z.string().describe('Subtask title'),
          status: z.number().optional().describe('0=normal, 1=completed'),
          startDate: z.string().optional().describe('Subtask start date'),
          isAllDay: z.boolean().optional().describe('All-day subtask'),
          sortOrder: z.number().optional().describe('Sort position'),
          timeZone: z.string().optional().describe('Time zone'),
        })
      )
      .optional()
      .describe('Updated subtask/checklist items'),
  },
  withErrorHandling('update_task', async ({ taskId, ...updates }) => {
    const task = await client.updateTask(taskId, updates);
    return { content: [{ type: 'text', text: JSON.stringify(task, null, 2) }] };
  })
);

server.tool(
  'complete_task',
  'Mark a task as completed',
  {
    projectId: z.string().describe('Project ID'),
    taskId: z.string().describe('Task ID to complete'),
  },
  withErrorHandling('complete_task', async ({ projectId, taskId }) => {
    await client.completeTask(projectId, taskId);
    return { content: [{ type: 'text', text: `Task ${taskId} marked as completed.` }] };
  })
);

server.tool(
  'delete_task',
  'Delete a task from TickTick',
  {
    projectId: z.string().describe('Project ID'),
    taskId: z.string().describe('Task ID to delete'),
  },
  withErrorHandling('delete_task', async ({ projectId, taskId }) => {
    await client.deleteTask(projectId, taskId);
    return { content: [{ type: 'text', text: `Task ${taskId} deleted.` }] };
  })
);

server.tool(
  'batch_create_tasks',
  'Create multiple tasks at once. Each task object supports the same fields as create_task.',
  {
    tasks: z
      .array(
        z.object({
          title: z.string().describe('Task title'),
          projectId: z.string().optional().describe('Project ID'),
          content: z.string().optional().describe('Content/notes'),
          desc: z.string().optional().describe('Description'),
          startDate: z.string().optional().describe('Start date (ISO 8601)'),
          dueDate: z.string().optional().describe('Due date (ISO 8601)'),
          isAllDay: z.boolean().optional().describe('All-day task'),
          priority: z.number().optional().describe('Priority: 0/1/3/5'),
          tags: z.array(z.string()).optional().describe('Tags'),
          timeZone: z.string().optional().describe('Time zone'),
          reminders: z.array(z.string()).optional().describe('Reminders'),
          repeatFlag: z.string().optional().describe('Recurrence rule'),
          items: z
            .array(
              z.object({
                title: z.string(),
                status: z.number().optional(),
                startDate: z.string().optional(),
                isAllDay: z.boolean().optional(),
                sortOrder: z.number().optional(),
                timeZone: z.string().optional(),
              })
            )
            .optional()
            .describe('Subtasks'),
        })
      )
      .describe('Array of task objects to create'),
  },
  withErrorHandling('batch_create_tasks', async ({ tasks }) => {
    const result = await client.batchCreateTasks(tasks);
    return { content: [{ type: 'text', text: JSON.stringify(result, null, 2) }] };
  })
);

// ─── Start ──────────────────────────────────────────────────────────────────

async function main() {
  log(`Starting... (node ${process.version}, pid ${process.pid})`);

  const transport = new StdioServerTransport();
  await server.connect(transport);
  log('Server connected');
}

main().catch((err) => {
  log('Fatal:', err);
  process.exit(1);
});
