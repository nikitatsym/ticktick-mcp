from __future__ import annotations

import os
import sys

import httpx

from .auth import (
    get_access_token,
    load_tokens,
    refresh_access_token,
    save_tokens,
)

API_BASE = "https://api.ticktick.com/open/v1"


def _log(msg: str) -> None:
    print(f"[ticktick-mcp] {msg}", file=sys.stderr)


class TickTickClient:
    def __init__(self, client_id: str | None, client_secret: str | None) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._access_token: str | None = None
        self._inbox_id: str | None = None
        self._http = httpx.AsyncClient(base_url=API_BASE, timeout=30)

    async def _token(self) -> str:
        if not self._access_token:
            self._access_token = await get_access_token(self._client_id, self._client_secret)
        return self._access_token

    async def _request(self, method: str, endpoint: str, body: dict | list | None = None) -> dict | list | None:
        token = await self._token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        res = await self._http.request(method, endpoint, headers=headers, json=body)

        # On 401, try refresh
        if res.status_code == 401:
            tokens = load_tokens()
            if tokens and tokens.get("refresh_token") and self._client_id and self._client_secret:
                try:
                    new_tokens = await refresh_access_token(
                        tokens["refresh_token"], self._client_id, self._client_secret
                    )
                    save_tokens(new_tokens)
                    self._access_token = new_tokens["access_token"]
                    headers["Authorization"] = f"Bearer {new_tokens['access_token']}"
                    res = await self._http.request(method, endpoint, headers=headers, json=body)
                except Exception:
                    pass  # refresh failed, return original 401

        if res.status_code >= 400:
            raise Exception(f"TickTick API error {res.status_code} {method} {endpoint}: {res.text}")

        content_type = res.headers.get("content-type", "")
        if "application/json" in content_type:
            return res.json()
        return None

    # ── Inbox ───────────────────────────────────────────────

    async def get_inbox_id(self) -> str:
        if self._inbox_id:
            return self._inbox_id

        # Create a throwaway task to discover inbox ID
        temp_task = await self.create_task({"title": "__ticktick_mcp_inbox_probe__"})
        self._inbox_id = temp_task["projectId"]

        # Clean up immediately
        try:
            await self.delete_task(temp_task["projectId"], temp_task["id"])
        except Exception:
            pass  # best effort

        return self._inbox_id

    async def get_inbox_with_data(self) -> dict:
        inbox_id = await self.get_inbox_id()
        return await self._request("GET", f"/project/{inbox_id}/data")

    # ── Projects ──────────────────────────────────────────────

    async def list_projects(self) -> list:
        return await self._request("GET", "/project")

    async def get_project(self, project_id: str) -> dict:
        return await self._request("GET", f"/project/{project_id}")

    async def get_project_with_data(self, project_id: str) -> dict:
        return await self._request("GET", f"/project/{project_id}/data")

    async def create_project(self, params: dict) -> dict:
        body = {"name": params["name"]}
        for key in ("color", "viewMode", "kind"):
            if params.get(key):
                body[key] = params[key]
        return await self._request("POST", "/project", body)

    async def update_project(self, project_id: str, updates: dict) -> dict:
        return await self._request("POST", f"/project/{project_id}", updates)

    async def delete_project(self, project_id: str) -> None:
        await self._request("DELETE", f"/project/{project_id}")

    # ── Tasks ─────────────────────────────────────────────────

    async def get_task(self, project_id: str, task_id: str) -> dict:
        return await self._request("GET", f"/project/{project_id}/task/{task_id}")

    async def create_task(self, task: dict) -> dict:
        return await self._request("POST", "/task", task)

    async def update_task(self, task_id: str, updates: dict) -> dict:
        return await self._request("POST", f"/task/{task_id}", updates)

    async def complete_task(self, project_id: str, task_id: str) -> None:
        await self._request("POST", f"/project/{project_id}/task/{task_id}/complete")

    async def delete_task(self, project_id: str, task_id: str) -> None:
        await self._request("DELETE", f"/project/{project_id}/task/{task_id}")

    async def batch_create_tasks(self, tasks: list[dict]) -> dict:
        return await self._request("POST", "/batch/task", {"add": tasks})
