from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.connectors.base import ConnectorBase
from app.schemas.pipeline import CompiledQueryPlan


class ERPNextConnector(ConnectorBase):
    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret

    def connect(self) -> None:
        return None

    def discover_schema(self) -> list[dict[str, Any]]:
        return []

    def execute_query(self, db: Session, plan: CompiledQueryPlan) -> dict[str, Any]:
        raise NotImplementedError("ERPNext connector execution is a real-source adapter and is intentionally not enabled in mock mode")

    def sync(self) -> None:
        return None


class GoogleSheetsConnector(ConnectorBase):
    def __init__(self, service_account_json: dict[str, Any]) -> None:
        self.service_account_json = service_account_json

    def connect(self) -> None:
        return None

    def discover_schema(self) -> list[dict[str, Any]]:
        return []

    def execute_query(self, db: Session, plan: CompiledQueryPlan) -> dict[str, Any]:
        raise NotImplementedError("Google Sheets connector execution is a real-source adapter and is intentionally not enabled in mock mode")

    def sync(self) -> None:
        return None
