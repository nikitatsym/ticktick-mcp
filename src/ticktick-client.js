const API_BASE = 'https://api.ticktick.com/open/v1';

export class TickTickClient {
  constructor(getToken, clientId, clientSecret) {
    this._getToken = getToken;
    this._clientId = clientId;
    this._clientSecret = clientSecret;
    this._accessToken = null;
  }

  async _token() {
    if (!this._accessToken) {
      const { getAccessToken } = await import('./auth.js');
      const result = await getAccessToken(this._clientId, this._clientSecret);
      this._accessToken = result.accessToken;
    }
    return this._accessToken;
  }

  /**
   * Make an authenticated API request. On 401, try to refresh token once.
   */
  async _request(method, endpoint, body = undefined) {
    const token = await this._token();
    const url = `${API_BASE}${endpoint}`;

    const headers = {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    };

    let res = await fetch(url, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // On 401, try refresh
    if (res.status === 401) {
      const { refreshAccessToken, loadTokens, saveTokens } = await import('./auth.js');
      const tokens = loadTokens();
      if (tokens?.refresh_token && this._clientId && this._clientSecret) {
        try {
          const newTokens = await refreshAccessToken(tokens.refresh_token, this._clientId, this._clientSecret);
          saveTokens(newTokens);
          this._accessToken = newTokens.access_token;

          res = await fetch(url, {
            method,
            headers: { ...headers, Authorization: `Bearer ${newTokens.access_token}` },
            body: body !== undefined ? JSON.stringify(body) : undefined,
          });
        } catch {
          // refresh failed, return original 401
        }
      }
    }

    if (!res.ok) {
      const text = await res.text();
      throw new Error(`TickTick API error ${res.status} ${method} ${endpoint}: ${text}`);
    }

    const contentType = res.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      return res.json();
    }
    // Some endpoints (complete, delete) return empty body
    return null;
  }

  // ── Projects ──────────────────────────────────────────────

  async listProjects() {
    return this._request('GET', '/project');
  }

  async getProject(projectId) {
    return this._request('GET', `/project/${projectId}`);
  }

  async getProjectWithData(projectId) {
    return this._request('GET', `/project/${projectId}/data`);
  }

  async createProject({ name, color, viewMode, kind }) {
    const body = { name };
    if (color) body.color = color;
    if (viewMode) body.viewMode = viewMode;
    if (kind) body.kind = kind;
    return this._request('POST', '/project', body);
  }

  async updateProject(projectId, updates) {
    return this._request('POST', `/project/${projectId}`, updates);
  }

  async deleteProject(projectId) {
    return this._request('DELETE', `/project/${projectId}`);
  }

  // ── Tasks ─────────────────────────────────────────────────

  async getTask(projectId, taskId) {
    return this._request('GET', `/project/${projectId}/task/${taskId}`);
  }

  async createTask(task) {
    return this._request('POST', '/task', task);
  }

  async updateTask(taskId, updates) {
    return this._request('POST', `/task/${taskId}`, updates);
  }

  async completeTask(projectId, taskId) {
    return this._request('POST', `/project/${projectId}/task/${taskId}/complete`);
  }

  async deleteTask(projectId, taskId) {
    return this._request('DELETE', `/project/${projectId}/task/${taskId}`);
  }

  async batchCreateTasks(tasks) {
    return this._request('POST', '/batch/task', { add: tasks });
  }
}
