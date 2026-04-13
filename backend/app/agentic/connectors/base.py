from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import hashlib
from typing import Any
from uuid import UUID

from app.agentic.core.audit_logger import AuditLogger
from app.agentic.models.audit_event import AuditEvent
from app.agentic.models.execution_plan import QueryFilter, ReadExecutionPlan, ScopeFilter, WriteExecutionPlan


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass(frozen=True)
class ConnectorHealth:
    status: HealthStatus
    latency_ms: float | None
    error: str | None = None
    last_checked_at: datetime | None = None


@dataclass(frozen=True)
class RawResult:
    rows: list[dict[str, Any]]
    row_count: int
    execution_time_ms: float
    source_schema: str


@dataclass(frozen=True)
class WriteResult:
    rows_affected: int
    generated_id: str | None
    execution_time_ms: float
    details: dict[str, Any] | None = None


class MissingScopeFilter(Exception):
    """Raised when a required scope filter is absent from ExecutionPlan."""


class ConnectorError(Exception):
    """Base class for connector errors."""


class ConnectorAuthError(ConnectorError):
    """Auth failure that must not trigger privileged retries."""


class ConnectorTimeoutError(ConnectorError):
    """Connector timed out and returned no partial data."""


class QueryInjectionAttempt(ConnectorError):
    """Input validation rejected a suspicious filter value."""


class ConnectorCapacityError(ConnectorError):
    """Connector pool is at configured capacity for this tenant."""


class BaseConnector(ABC):
    """Abstract base for all tenant-scoped connectors."""

    def __init__(self, tenant_id: UUID, config: dict[str, Any]):
        self._tenant_id = tenant_id
        self._config = dict(config)
        self._connected = False
        self._audit = AuditLogger()
        self._validate_config(self._config)

    @property
    def tenant_id(self) -> UUID:
        return self._tenant_id

    @property
    def connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self) -> None:
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        ...

    @abstractmethod
    async def discover_schema(self) -> dict[str, Any]:
        ...

    @abstractmethod
    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        ...

    @abstractmethod
    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        ...

    @abstractmethod
    async def health_check(self) -> ConnectorHealth:
        ...

    def _validate_scope(self, scope: ScopeFilter) -> None:
        if not scope.tenant_id:
            raise MissingScopeFilter("tenant_id is required in every ExecutionPlan scope")
        if str(scope.tenant_id) != str(self._tenant_id):
            raise MissingScopeFilter(
                f"Scope tenant_id {scope.tenant_id} does not match connector tenant_id {self._tenant_id}"
            )

    def _validate_scope_filters(
        self,
        filters: list[QueryFilter],
        scope: ScopeFilter,
        scope_filters_required: bool,
    ) -> None:
        if not scope_filters_required:
            return
        if not filters:
            raise MissingScopeFilter("Scope filters are required but missing from execution plan")

        allowed_values = {
            str(scope.user_alias or ""),
            str(scope.department_id or ""),
            str(scope.tenant_id or ""),
        }

        def _value_matches_scope(value: Any) -> bool:
            if isinstance(value, (list, tuple, set)):
                return any(str(item) in allowed_values for item in value)
            return str(value) in allowed_values

        if not any(_value_matches_scope(item.value) for item in filters):
            raise MissingScopeFilter("Scope filters do not include any validated caller scope values")

    def _validate_filter_values(self, filters: list[QueryFilter]) -> None:
        injection_patterns = ["'", '"', ";", "--", "/*", "*/", "xp_", "exec", "drop"]
        for item in filters:
            value = item.value
            if not isinstance(value, str):
                continue
            lowered = value.lower()
            for pattern in injection_patterns:
                if pattern in lowered:
                    raise QueryInjectionAttempt(
                        f"Suspicious pattern '{pattern}' in filter value for field '{item.field}'"
                    )

    def _ensure_connected(self) -> None:
        if not self._connected:
            raise ConnectorError("Connector must connect() before use")

    def _validate_config(self, config: dict[str, Any]) -> None:
        del config

    async def _audit_execution(
        self,
        *,
        event_type: str,
        action_id: str,
        user_alias: str,
        status: str,
        fields: list[str],
        row_count: int,
        execution_time_ms: float,
        source_alias: str,
        payload: dict[str, Any] | None = None,
        error: str | None = None,
        critical: bool = False,
    ) -> None:
        payload_hash = None
        if payload:
            digest_parts = []
            for key, value in sorted(payload.items()):
                value_hash = hashlib.sha256(str(value).encode("utf-8")).hexdigest()
                digest_parts.append(f"{key}:{value_hash}")
            payload_hash = hashlib.sha256("|".join(digest_parts).encode("utf-8")).hexdigest()

        try:
            await self._audit.write(
                AuditEvent(
                    event_type=event_type,
                    action_id=action_id,
                    user_alias=user_alias,
                    tenant_id=self._tenant_id,
                    status=status,
                    payload_hash=payload_hash,
                    data_accessed=fields,
                    metadata={
                        "connector_type": type(self).__name__,
                        "row_count": row_count,
                        "execution_time_ms": execution_time_ms,
                        "source_alias": source_alias,
                        "error": error,
                    },
                )
            )
        except Exception as exc:
            if critical:
                raise ConnectorError("Critical audit persistence failure") from exc
            return
