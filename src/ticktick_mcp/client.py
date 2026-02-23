import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from .auth import get_access_token, load_tokens, refresh_access_token, save_tokens

API_BASE = "https://api.ticktick.com/open/v1"


class TickTickClient:
    def __init__(self, client_id, client_secret):
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token = None
        self._inbox_id = None

    def _token(self):
        if not self._access_token:
            self._access_token = get_access_token(self._client_id, self._client_secret)
        return self._access_token

    def _do_http(self, method, endpoint, token, body=None):
        url = f"{API_BASE}{endpoint}"
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req) as res:
                raw = res.read()
                ct = res.headers.get("content-type", "")
                if "application/json" in ct and raw:
                    return res.status, json.loads(raw)
                return res.status, None
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")

    def _request(self, method, endpoint, body=None):
        token = self._token()
        status, data = self._do_http(method, endpoint, token, body)

        # On 401, try refresh
        if status == 401:
            tokens = load_tokens()
            if tokens and tokens.get("refresh_token") and self._client_id and self._client_secret:
                try:
                    new_tokens = refresh_access_token(tokens["refresh_token"], self._client_id, self._client_secret)
                    save_tokens(new_tokens)
                    self._access_token = new_tokens["access_token"]
                    status, data = self._do_http(method, endpoint, new_tokens["access_token"], body)
                except Exception:
                    pass

        if status >= 400:
            raise Exception(f"TickTick API error {status} {method} {endpoint}: {data}")
        return data

    # ── Inbox ───────────────────────────────────────────────

    def get_inbox_id(self):
        if self._inbox_id:
            return self._inbox_id
        temp_task = self.create_task({"title": "__ticktick_mcp_inbox_probe__"})
        self._inbox_id = temp_task["projectId"]
        try:
            self.delete_task(temp_task["projectId"], temp_task["id"])
        except Exception:
            pass
        return self._inbox_id

    def get_inbox_with_data(self):
        inbox_id = self.get_inbox_id()
        return self._request("GET", f"/project/{inbox_id}/data")

    # ── Projects ──────────────────────────────────────────────

    def list_projects(self):
        return self._request("GET", "/project")

    def get_project(self, project_id):
        return self._request("GET", f"/project/{project_id}")

    def get_project_with_data(self, project_id):
        return self._request("GET", f"/project/{project_id}/data")

    def create_project(self, params):
        body = {"name": params["name"]}
        for key in ("color", "viewMode", "kind"):
            if params.get(key):
                body[key] = params[key]
        return self._request("POST", "/project", body)

    def update_project(self, project_id, updates):
        return self._request("POST", f"/project/{project_id}", updates)

    def delete_project(self, project_id):
        return self._request("DELETE", f"/project/{project_id}")

    # ── Tasks ─────────────────────────────────────────────────

    def get_task(self, project_id, task_id):
        return self._request("GET", f"/project/{project_id}/task/{task_id}")

    def create_task(self, task):
        return self._request("POST", "/task", task)

    def update_task(self, task_id, updates):
        return self._request("POST", f"/task/{task_id}", updates)

    def complete_task(self, project_id, task_id):
        return self._request("POST", f"/project/{project_id}/task/{task_id}/complete")

    def delete_task(self, project_id, task_id):
        return self._request("DELETE", f"/project/{project_id}/task/{task_id}")

    def batch_create_tasks(self, tasks):
        return self._request("POST", "/batch/task", {"add": tasks})

    # ── Today ─────────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str):
        """Parse TickTick date string into a datetime object."""
        if not date_str:
            return None
        # TickTick uses formats like "2024-01-15T09:00:00.000+0000"
        clean = date_str.replace("+0000", "+00:00").replace("+00:00:00", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except ValueError:
            return None

    def get_today_tasks(self):
        """Get all uncompleted tasks due today or earlier (overdue)."""
        now = datetime.now(timezone.utc)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        projects = self._request("GET", "/project") or []
        # Include inbox
        inbox_id = self.get_inbox_id()
        project_ids = [inbox_id] + [p["id"] for p in projects]

        tasks = []
        seen = set()
        for pid in project_ids:
            try:
                data = self._request("GET", f"/project/{pid}/data")
            except Exception:
                continue
            for task in data.get("tasks", []):
                if task["id"] in seen:
                    continue
                seen.add(task["id"])
                # status 0 = normal, 2 = completed
                if task.get("status", 0) == 2:
                    continue
                due = self._parse_date(task.get("dueDate"))
                if due and due <= end_of_today:
                    tasks.append(task)

        tasks.sort(key=lambda t: t.get("dueDate") or "")
        return tasks
