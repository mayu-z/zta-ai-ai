from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings, get_settings


class TicketingClient(Protocol):
    def create_ticket(self, title: str, description: str, metadata: dict) -> str:
        ...

    def update_ticket(self, ticket_id: str, status: str, comment: str) -> bool:
        ...


@dataclass
class JiraTicketing:
    base_url: str
    token: str

    def create_ticket(self, title: str, description: str, metadata: dict) -> str:
        payload = {
            "fields": {
                "summary": title,
                "description": f"{description}\n\nMetadata: {metadata}",
                "issuetype": {"name": "Task"},
                "project": {"key": metadata.get("project_key", "OPS")},
            }
        }
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/rest/api/3/issue",
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(f"Jira create_ticket failed: {response.status_code} {response.text}")
            body = response.json()
            return str(body.get("key") or body.get("id") or f"JIRA-{uuid.uuid4().hex[:8]}")

    def update_ticket(self, ticket_id: str, status: str, comment: str) -> bool:
        payload = {"body": f"[{status}] {comment}"}
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/rest/api/3/issue/{ticket_id}/comment",
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                json=payload,
            )
            return response.status_code < 400


@dataclass
class ServiceNowTicketing:
    base_url: str
    user: str
    password: str

    def create_ticket(self, title: str, description: str, metadata: dict) -> str:
        payload = {
            "short_description": title,
            "description": description,
            "u_metadata": metadata,
        }
        with httpx.Client(timeout=10.0, auth=(self.user, self.password)) as client:
            response = client.post(
                f"{self.base_url.rstrip('/')}/api/now/table/incident",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            if response.status_code >= 400:
                raise RuntimeError(
                    f"ServiceNow create_ticket failed: {response.status_code} {response.text}"
                )
            body = response.json()
            result = body.get("result", {})
            return str(result.get("number") or result.get("sys_id") or f"SN-{uuid.uuid4().hex[:8]}")

    def update_ticket(self, ticket_id: str, status: str, comment: str) -> bool:
        payload = {
            "comments": comment,
            "state": status,
        }
        with httpx.Client(timeout=10.0, auth=(self.user, self.password)) as client:
            response = client.patch(
                f"{self.base_url.rstrip('/')}/api/now/table/incident/{ticket_id}",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            return response.status_code < 400


class NoOpTicketing:
    def create_ticket(self, title: str, description: str, metadata: dict) -> str:
        _ = (title, description, metadata)
        return f"NOOP-{uuid.uuid4().hex[:12]}"

    def update_ticket(self, ticket_id: str, status: str, comment: str) -> bool:
        _ = (ticket_id, status, comment)
        return True


def get_ticketing_client(settings: Settings | None = None) -> TicketingClient:
    resolved = settings or get_settings()
    provider = (resolved.ticketing_provider or "none").strip().lower()
    if provider == "jira":
        return JiraTicketing(base_url=resolved.jira_base_url, token=resolved.jira_token)
    if provider == "servicenow":
        return ServiceNowTicketing(
            base_url=resolved.sn_base_url,
            user=resolved.sn_user,
            password=resolved.sn_pass,
        )
    return NoOpTicketing()
