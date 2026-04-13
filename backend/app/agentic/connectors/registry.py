from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from app.core.config import get_settings

from .base import BaseConnector, ConnectorCapacityError, ConnectorError, HealthStatus


CONNECTOR_REGISTRY: dict[str, type[BaseConnector]] = {}


def register_default_connectors() -> None:
    if CONNECTOR_REGISTRY:
        return

    from .calendar import GoogleCalendarConnector, MicrosoftCalendarConnector, MockCalendarConnector
    from .erpnext import ERPNextConnector
    from .mock import MockConnector
    from .mysql import MariaDBConnector, MySQLConnector
    from .postgres import PostgresConnector
    from .smtp import SMTPConnector
    from .upi import UPIGatewayConnector

    CONNECTOR_REGISTRY.update(
        {
            "postgres": PostgresConnector,
            "mysql": MySQLConnector,
            "mariadb": MariaDBConnector,
            "erpnext": ERPNextConnector,
            "upi_gateway": UPIGatewayConnector,
            "smtp": SMTPConnector,
            "calendar_google": GoogleCalendarConnector,
            "calendar_ms": MicrosoftCalendarConnector,
            "calendar_mock": MockCalendarConnector,
            "mock": MockConnector,
        }
    )


class ConnectorPool:
    """Async connector lifecycle manager with strict tenant isolation."""

    def __init__(self, max_idle_seconds: int = 300, max_per_tenant: int = 10):
        self._pool: dict[str, BaseConnector] = {}
        self._last_used: dict[str, datetime] = {}
        self._max_idle = max_idle_seconds
        self._max_per_tenant = max_per_tenant
        self._lock = asyncio.Lock()

    def _pool_key(self, tenant_id: UUID, source_type: str, source_id: str) -> str:
        return f"{tenant_id}:{source_type}:{source_id}"

    async def get(
        self,
        tenant_id: UUID,
        source_type: str,
        source_id: str,
        config: dict[str, Any],
    ) -> BaseConnector:
        register_default_connectors()
        pool_key = self._pool_key(tenant_id, source_type, source_id)

        async with self._lock:
            await self._purge_idle_locked()

            if pool_key in self._pool:
                connector = self._pool[pool_key]
                health = await connector.health_check()
                if health.status != HealthStatus.DOWN:
                    self._last_used[pool_key] = datetime.now(tz=UTC)
                    return connector
                await connector.disconnect()
                self._pool.pop(pool_key, None)
                self._last_used.pop(pool_key, None)

            tenant_count = sum(
                1 for key in self._pool.keys() if key.startswith(f"{tenant_id}:")
            )
            if tenant_count >= self._max_per_tenant:
                raise ConnectorCapacityError(f"Connector pool at capacity for tenant {tenant_id}")

            connector_class = CONNECTOR_REGISTRY.get(source_type)
            if connector_class is None:
                raise ConnectorError(f"Unknown source_type: {source_type}")

            environment = get_settings().environment.strip().lower()
            if environment == "production" and source_type in {"mock", "calendar_mock"}:
                raise ConnectorError(f"Mock source_type '{source_type}' is not allowed in production")

            connector = connector_class(tenant_id=tenant_id, config=config)
            await connector.connect()
            self._pool[pool_key] = connector
            self._last_used[pool_key] = datetime.now(tz=UTC)
            return connector

    async def release(self, tenant_id: UUID, source_type: str, source_id: str) -> None:
        pool_key = self._pool_key(tenant_id, source_type, source_id)
        async with self._lock:
            connector = self._pool.pop(pool_key, None)
            self._last_used.pop(pool_key, None)
            if connector is not None:
                await connector.disconnect()

    async def _purge_idle_locked(self) -> None:
        if self._max_idle <= 0:
            return
        cutoff = datetime.now(tz=UTC) - timedelta(seconds=self._max_idle)
        stale_keys = [key for key, ts in self._last_used.items() if ts < cutoff]
        for key in stale_keys:
            connector = self._pool.pop(key, None)
            self._last_used.pop(key, None)
            if connector is not None:
                await connector.disconnect()
