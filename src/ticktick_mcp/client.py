"""TickTick Open API client built on httpx."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, cast

import httpx

from .auth import get_access_token
from .types import ProjectDataDict, ProjectDict, TaskDict

API_BASE = "https://api.ticktick.com/open/v1"


class TickTickError(Exception):
    """Raised on 4xx/5xx responses from the TickTick Open API.

    Carries enough context to diagnose the failure without re-issuing the
    request: HTTP status, method, path (after rewrites), and the decoded
    response body (JSON when possible, else text).
    """

    def __init__(self, status: int, method: str, path: str, body: Any):
        self.status = status
        self.method = method
        self.path = path
        self.body = body
        super().__init__(f"TickTick API {status} {method} {path}: {body}")


class TickTickClient:
    def __init__(self) -> None:
        self._inbox_id: str | None = None
        token = get_access_token()
        self._http = httpx.Client(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def _request(self, method: str, path: str, json: Any = None) -> Any:
        r = self._http.request(method, path, json=json)
        if r.status_code >= 400:
            try:
                body: Any = r.json()
            except Exception:
                body = r.text
            raise TickTickError(r.status_code, method, path, body)
        if r.status_code == 204 or not r.content:
            return None
        return r.json()

    # ── Inbox ───────────────────────────────────────────

    def get_inbox_id(self) -> str:
        if self._inbox_id:
            return self._inbox_id
        temp_task = self.create_task({"title": "__ticktick_mcp_inbox_probe__"})
        self._inbox_id = temp_task["projectId"]
        try:
            self.delete_task(self._inbox_id, temp_task["id"])
        except Exception:
            pass
        return self._inbox_id

    def get_inbox_with_data(self) -> ProjectDataDict:
        inbox_id = self.get_inbox_id()
        return cast(ProjectDataDict, self._request("GET", f"/project/{inbox_id}/data"))

    # ── Projects ──────────────────────────────────────────

    def list_projects(self) -> list[ProjectDict]:
        return cast("list[ProjectDict]", self._request("GET", "/project") or [])

    def get_project(self, project_id: str) -> ProjectDict:
        return cast(ProjectDict, self._request("GET", f"/project/{project_id}"))

    def get_project_with_data(self, project_id: str) -> ProjectDataDict:
        return cast(ProjectDataDict, self._request("GET", f"/project/{project_id}/data"))

    def create_project(self, payload: dict[str, Any]) -> ProjectDict:
        body: dict[str, Any] = {"name": payload["name"]}
        for key in ("color", "viewMode", "kind"):
            if payload.get(key) is not None:
                body[key] = payload[key]
        return cast(ProjectDict, self._request("POST", "/project", body))

    def update_project(self, project_id: str, updates: dict[str, Any]) -> ProjectDict:
        return cast(ProjectDict, self._request("POST", f"/project/{project_id}", updates))

    def delete_project(self, project_id: str) -> None:
        self._request("DELETE", f"/project/{project_id}")

    # ── Tasks ─────────────────────────────────────────────

    def get_task(self, project_id: str, task_id: str) -> TaskDict:
        return cast(TaskDict, self._request("GET", f"/project/{project_id}/task/{task_id}"))

    def create_task(self, task: dict[str, Any]) -> TaskDict:
        return cast(TaskDict, self._request("POST", "/task", task))

    def update_task(self, task_id: str, updates: dict[str, Any]) -> TaskDict:
        return cast(TaskDict, self._request("POST", f"/task/{task_id}", updates))

    def complete_task(self, project_id: str, task_id: str) -> None:
        self._request("POST", f"/project/{project_id}/task/{task_id}/complete")

    def delete_task(self, project_id: str, task_id: str) -> None:
        self._request("DELETE", f"/project/{project_id}/task/{task_id}")

    # ── Today ─────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str | None) -> datetime | None:
        """Parse a TickTick date string (e.g. '2024-01-15T09:00:00.000+0000')."""
        if not date_str:
            return None
        clean = date_str.replace("+0000", "+00:00").replace("+00:00:00", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except ValueError:
            return None

    def get_today_tasks(self) -> list[TaskDict]:
        """All uncompleted tasks due today or earlier (overdue)."""
        now = datetime.now(timezone.utc)
        end_of_today = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        projects = self.list_projects()
        inbox_id = self.get_inbox_id()
        project_ids: list[str] = [inbox_id] + [
            p["id"] for p in projects if "id" in p
        ]

        tasks: list[TaskDict] = []
        seen: set[str] = set()
        for pid in project_ids:
            try:
                data = self.get_project_with_data(pid)
            except Exception:
                continue
            for task in data.get("tasks") or []:
                tid = task.get("id") or ""
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                if task.get("status", 0) == 2:
                    continue
                due = self._parse_date(task.get("dueDate"))
                if due and due <= end_of_today:
                    tasks.append(task)

        tasks.sort(key=lambda t: t.get("dueDate") or "")
        return tasks
