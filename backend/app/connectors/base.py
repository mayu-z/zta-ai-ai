from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.schemas.pipeline import CompiledQueryPlan


CONNECTOR_ERROR_CODES = {
    "SUCCESS": 200,
    "CLIENT_ERROR": 400,
    "AUTHENTICATION_ERROR": 401,
    "AUTHORIZATION_ERROR": 403,
    "NOT_FOUND": 404,
    "RATE_LIMITED": 429,
    "SERVER_ERROR": 500,
    "TIMEOUT": 504,
}


@dataclass(slots=True)
class QueryResult:
    rows: list[dict[str, Any]]
    count: int
    latency_ms: int
    total_rows_available: int
    truncated: bool
    warnings: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ConnectionStatus:
    status: str
    response_time_ms: int
    error: str | None = None
    is_temporary: bool = False


@dataclass(slots=True)
class TestResult:
    status: str
    latency_ms: int
    error: str | None = None


@dataclass(slots=True)
class SyncResult:
    status: str
    tables_discovered: int
    tables_added: int
    tables_removed: int
    fields_changed: int
    duration_ms: int
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class HealthStatus:
    status: str
    last_query_latency_ms: int
    consecutive_failures: int
    last_failure_at: str | None
    recommendation: str


@dataclass(slots=True)
class ConnectionInfo:
    connector_id: str
    tenant_id: str | None
    source_type: str
    supports_sync: bool = True
    supports_live_queries: bool = True


class ConnectorBase(ABC):
    @abstractmethod
    def connect(self, timeout_seconds: int = 30) -> ConnectionStatus: ...

    def test_connection(self, timeout_seconds: int = 30) -> TestResult:
        status = self.connect(timeout_seconds=timeout_seconds)
        if status.status == "connected":
            return TestResult(status="healthy", latency_ms=status.response_time_ms)
        return TestResult(
            status="error",
            latency_ms=status.response_time_ms,
            error=status.error,
        )

    @abstractmethod
    def discover_schema(self, force_refresh: bool = False) -> list[dict[str, Any]]: ...

    @abstractmethod
    def execute_query(
        self,
        db: Session,
        plan: CompiledQueryPlan,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def sync(self) -> SyncResult: ...

    @abstractmethod
    def health_check(self) -> HealthStatus: ...

    @abstractmethod
    def get_connection_info(self) -> ConnectionInfo: ...
