"""TickTick Open API client built on httpx."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, cast

import httpx

from .auth import get_access_token
from .types import ProjectDataDict, ProjectDict, TaskDict

API_BASE = "https://api.ticktick.com/open/v1"

_log = logging.getLogger("ticktick_mcp.client")


class TickTickError(Exception):
    """Raised on 4xx/5xx responses from the TickTick Open API, and on empty 2xx bodies where JSON was expected.

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


def _check_error(r: httpx.Response, method: str, path: str) -> None:
    if r.status_code < 400:
        return
    try:
        body: Any = r.json()
    # r.json() decodes bytes, so a non-UTF-8 error page raises
    # UnicodeDecodeError, not JSONDecodeError. ValueError covers both.
    except ValueError:
        body = r.text
    raise TickTickError(r.status_code, method, path, body)


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
        _check_error(r, method, path)
        if r.status_code == 204 or not r.content:
            raise TickTickError(
                r.status_code, method, path, "empty response body (expected JSON)"
            )
        return r.json()

    def _request_no_content(self, method: str, path: str) -> None:
        """Endpoints whose success shape is 204 or an empty 2xx body; any body is ignored."""
        r = self._http.request(method, path)
        _check_error(r, method, path)

    # ── Inbox ───────────────────────────────────────────

    def get_inbox_id(self) -> str:
        if self._inbox_id:
            return self._inbox_id
        temp_task = self.create_task({"title": "__ticktick_mcp_inbox_probe__"})
        self._inbox_id = temp_task["projectId"]
        temp_id = temp_task["id"]
        try:
            self.delete_task(self._inbox_id, temp_id)
        except Exception:  # noqa: BLE001 - the id is already in hand; cleanup must not cost the caller its answer
            _log.warning(
                "inbox probe task %s left behind in project %s",
                temp_id, self._inbox_id, exc_info=True,
            )
        return self._inbox_id

    def get_inbox_with_data(self) -> ProjectDataDict:
        inbox_id = self.get_inbox_id()
        return cast(ProjectDataDict, self._request("GET", f"/project/{inbox_id}/data"))

    # ── Projects ──────────────────────────────────────────

    def list_projects(self) -> list[ProjectDict]:
        return cast("list[ProjectDict]", self._request("GET", "/project"))

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
        self._request_no_content("DELETE", f"/project/{project_id}")

    # ── Tasks ─────────────────────────────────────────────

    def get_task(self, project_id: str, task_id: str) -> TaskDict:
        return cast(TaskDict, self._request("GET", f"/project/{project_id}/task/{task_id}"))

    def create_task(self, task: dict[str, Any]) -> TaskDict:
        return cast(TaskDict, self._request("POST", "/task", task))

    def update_task(self, task_id: str, updates: dict[str, Any]) -> TaskDict:
        return cast(TaskDict, self._request("POST", f"/task/{task_id}", updates))

    def complete_task(self, project_id: str, task_id: str) -> None:
        self._request_no_content("POST", f"/project/{project_id}/task/{task_id}/complete")

    def delete_task(self, project_id: str, task_id: str) -> None:
        self._request_no_content("DELETE", f"/project/{project_id}/task/{task_id}")

    # ── Today ─────────────────────────────────────────────

    @staticmethod
    def _parse_date(date_str: str | None, task_id: str = "") -> datetime | None:
        """Parse a TickTick date string (e.g. '2024-01-15T09:00:00.000+0000').

        None means the task carries no date. A date that will not parse is a
        break in TickTick's format, not an absent one: returning None for it
        would drop the task from a due-date filter that promises every match.
        """
        if not date_str:
            return None
        clean = date_str.replace("+0000", "+00:00").replace("+00:00:00", "+00:00")
        try:
            return datetime.fromisoformat(clean)
        except ValueError as e:
            where = f" on task {task_id}" if task_id else ""
            raise ValueError(f"unparseable TickTick date {date_str!r}{where}") from e

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
            # No skip-on-error: this returns "all tasks due today", so a project
            # that fails to load must fail the call, not silently shrink it.
            # TickTickError names the offending /project/{pid}/data path.
            data = self.get_project_with_data(pid)
            for task in data.get("tasks") or []:
                tid = task.get("id") or ""
                if not tid or tid in seen:
                    continue
                seen.add(tid)
                if task.get("status", 0) == 2:
                    continue
                due = self._parse_date(task.get("dueDate"), tid)
                if due and due <= end_of_today:
                    tasks.append(task)

        tasks.sort(key=lambda t: t.get("dueDate") or "")
        return tasks
