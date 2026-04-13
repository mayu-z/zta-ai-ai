from __future__ import annotations

import asyncio
from datetime import UTC, datetime
import time
from typing import Any

from sqlalchemy import MetaData, Table, bindparam, delete, insert, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.sql import Select

from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ReadExecutionPlan, WriteExecutionPlan
from app.core.secret_manager import secret_manager

from .base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorError,
    ConnectorHealth,
    ConnectorTimeoutError,
    HealthStatus,
    MissingScopeFilter,
    QueryInjectionAttempt,
    RawResult,
    WriteResult,
)


class PostgresConnector(BaseConnector):
    def __init__(self, tenant_id, config: dict[str, Any]):
        super().__init__(tenant_id=tenant_id, config=config)
        self._engine: AsyncEngine | None = None
        self._table_cache: dict[str, Table] = {}
        self._metadata = MetaData()

    async def connect(self) -> None:
        dsn = self._resolve_connection_url()
        if not dsn:
            raise ConnectorAuthError("Missing PostgreSQL credential in secrets manager")

        try:
            self._engine = create_async_engine(
                dsn,
                pool_size=3,
                max_overflow=5,
                pool_pre_ping=True,
                future=True,
            )
            await self._ping()
            self._connected = True
        except ConnectorAuthError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise self._map_db_error(exc) from exc

    async def disconnect(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
        self._engine = None
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        self._ensure_connected()
        assert self._engine is not None

        columns_sql = text(
            """
            SELECT
              table_name,
              column_name,
              data_type,
              is_nullable
            FROM information_schema.columns
            WHERE table_schema = current_schema()
            ORDER BY table_name, ordinal_position
            """
        )

        classifications: dict[tuple[str, str], str] = {}
        schema: dict[str, dict[str, dict[str, Any]]] = {}
        try:
            async with self._engine.connect() as conn:
                try:
                    meta_rows = (
                        await conn.execute(
                            text(
                                """
                                SELECT table_name, field_name, classification
                                FROM schema_metadata
                                """
                            )
                        )
                    ).mappings().all()
                    for row in meta_rows:
                        classifications[(str(row["table_name"]), str(row["field_name"]))] = str(
                            row["classification"]
                        )
                except Exception:
                    pass

                rows = (await conn.execute(columns_sql)).mappings().all()
                for row in rows:
                    table_name = str(row["table_name"])
                    column_name = str(row["column_name"])
                    schema.setdefault(table_name, {})[column_name] = {
                        "type": str(row["data_type"]),
                        "classification": classifications.get((table_name, column_name), "GENERAL"),
                        "nullable": str(row["is_nullable"]).upper() == "YES",
                    }
        except Exception as exc:  # noqa: BLE001
            raise self._map_db_error(exc) from exc
        return schema

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_filter_values(plan.filters)
        assert self._engine is not None

        started = time.perf_counter()
        try:
            table = await self._get_table(plan.entity)
            stmt, params = self._build_select(plan=plan, table=table)
            async with self._engine.connect() as conn:
                rows = (await conn.execute(stmt, params)).mappings().all()

            elapsed = (time.perf_counter() - started) * 1000
            mapped_rows = [dict(row) for row in rows]
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(mapped_rows[0].keys()) if mapped_rows else list(plan.fields),
                row_count=len(mapped_rows),
                execution_time_ms=elapsed,
                source_alias=plan.entity,
            )
            return RawResult(
                rows=mapped_rows,
                row_count=len(mapped_rows),
                execution_time_ms=elapsed,
                source_schema=plan.entity,
            )
        except (MissingScopeFilter, QueryInjectionAttempt):
            raise
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_db_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(plan.fields),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=plan.entity,
                error=str(mapped),
            )
            raise mapped from exc

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_filter_values(plan.filters)
        assert self._engine is not None

        started = time.perf_counter()
        try:
            table = await self._get_table(plan.entity)
            stmt, params = self._build_write(plan=plan, table=table)
            async with self._engine.begin() as conn:
                result = await conn.execute(stmt, params)

            elapsed = (time.perf_counter() - started) * 1000
            rows_affected = int(result.rowcount or 0)
            generated_id = None
            if plan.operation == "INSERT":
                inserted = getattr(result, "inserted_primary_key", None)
                if inserted:
                    generated_id = str(inserted[0])

            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(plan.payload.keys()),
                row_count=rows_affected,
                execution_time_ms=elapsed,
                source_alias=plan.entity,
                payload=plan.payload,
            )
            return WriteResult(
                rows_affected=rows_affected,
                generated_id=generated_id,
                execution_time_ms=elapsed,
            )
        except (MissingScopeFilter, QueryInjectionAttempt):
            raise
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_db_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(plan.payload.keys()),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=plan.entity,
                payload=plan.payload,
                error=str(mapped),
            )
            raise mapped from exc

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            await asyncio.wait_for(self._ping(), timeout=2.0)
            elapsed = (time.perf_counter() - started) * 1000
            return ConnectorHealth(
                status=HealthStatus.HEALTHY,
                latency_ms=elapsed,
                last_checked_at=datetime.now(tz=UTC),
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            return ConnectorHealth(
                status=HealthStatus.DOWN,
                latency_ms=elapsed,
                error=str(exc),
                last_checked_at=datetime.now(tz=UTC),
            )

    def _build_select(self, plan: ReadExecutionPlan, table: Table) -> tuple[Select, dict[str, Any]]:
        if plan.fields:
            selected = [table.c[field] for field in plan.fields if field in table.c]
            stmt = select(*selected) if selected else select(table)
        else:
            stmt = select(table)

        params: dict[str, Any] = {"tenant_id": str(self.tenant_id)}
        if "tenant_id" not in table.c:
            raise MissingScopeFilter(f"Table '{table.name}' does not expose tenant_id column")

        stmt = stmt.where(table.c.tenant_id == bindparam("tenant_id"))
        for index, query_filter in enumerate(plan.filters):
            expression, filter_params = self._column_expression(table, query_filter, index)
            stmt = stmt.where(expression)
            params.update(filter_params)

        if plan.order_by and plan.order_by in table.c:
            stmt = stmt.order_by(table.c[plan.order_by])

        bounded_limit = min(max(plan.limit, 1), 1000)
        bounded_offset = max(plan.offset, 0)
        stmt = stmt.limit(bounded_limit).offset(bounded_offset)
        return stmt, params

    def _build_write(self, plan: WriteExecutionPlan, table: Table):
        params: dict[str, Any] = {}
        if "tenant_id" not in table.c:
            raise MissingScopeFilter(f"Table '{table.name}' does not expose tenant_id column")

        operation = plan.operation.upper()
        if operation == "INSERT":
            payload = dict(plan.payload)
            payload["tenant_id"] = str(self.tenant_id)
            return insert(table).values(**payload), {}

        stmt = update(table) if operation == "UPDATE" else delete(table)
        stmt = stmt.where(table.c.tenant_id == bindparam("tenant_id"))
        params["tenant_id"] = str(self.tenant_id)

        for index, query_filter in enumerate(plan.filters):
            expression, filter_params = self._column_expression(table, query_filter, index)
            stmt = stmt.where(expression)
            params.update(filter_params)

        if operation == "UPDATE":
            stmt = stmt.values(**dict(plan.payload))
        return stmt, params

    async def _get_table(self, entity: str) -> Table:
        if entity in self._table_cache:
            return self._table_cache[entity]
        assert self._engine is not None

        async with self._engine.connect() as conn:
            table = await conn.run_sync(
                lambda sync_conn: Table(entity, self._metadata, autoload_with=sync_conn, extend_existing=True)
            )
        self._table_cache[entity] = table
        return table

    def _column_expression(
        self,
        table: Table,
        query_filter: QueryFilter,
        index: int,
    ):
        if query_filter.field not in table.c:
            raise ConnectorError(f"Unknown field '{query_filter.field}' for entity '{table.name}'")

        column = table.c[query_filter.field]
        operator = query_filter.operator
        param_name = f"f_{index}"
        value = query_filter.value

        if operator == FilterOperator.EQ:
            return column == bindparam(param_name), {param_name: value}
        if operator == FilterOperator.NEQ:
            return column != bindparam(param_name), {param_name: value}
        if operator == FilterOperator.GT:
            return column > bindparam(param_name), {param_name: value}
        if operator == FilterOperator.GTE:
            return column >= bindparam(param_name), {param_name: value}
        if operator == FilterOperator.LT:
            return column < bindparam(param_name), {param_name: value}
        if operator == FilterOperator.LTE:
            return column <= bindparam(param_name), {param_name: value}
        if operator == FilterOperator.LIKE:
            return column.like(bindparam(param_name)), {param_name: value}
        if operator == FilterOperator.IN:
            values = list(value) if isinstance(value, (list, tuple, set)) else [value]
            return column.in_(bindparam(param_name, expanding=True)), {param_name: values}
        if operator == FilterOperator.IS_NULL:
            if bool(value):
                return column.is_(None), {}
            return column.is_not(None), {}

        raise ConnectorError(f"Unsupported operator '{operator}'")

    async def _ping(self) -> None:
        if self._engine is None:
            raise ConnectorError("Engine is not initialized")
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            raise self._map_db_error(exc) from exc

    def _resolve_connection_url(self) -> str:
        secret_key = f"postgres:{self.tenant_id}"
        fallback = str(self._config.get("connection_url") or self._config.get("database_url") or "")
        raw = secret_manager.get_secret(secret_key, fallback=fallback).strip()
        if raw.startswith("postgres://"):
            return "postgresql+asyncpg://" + raw[len("postgres://") :]
        if raw.startswith("postgresql+psycopg2://"):
            return "postgresql+asyncpg://" + raw[len("postgresql+psycopg2://") :]
        if raw.startswith("postgresql://") and "+asyncpg" not in raw:
            return "postgresql+asyncpg://" + raw[len("postgresql://") :]
        return raw

    def _map_db_error(self, exc: Exception) -> ConnectorError:
        message = str(exc).lower()
        if "auth" in message or "password" in message or "permission denied" in message:
            return ConnectorAuthError(str(exc))
        if "timeout" in message or "timed out" in message:
            return ConnectorTimeoutError(str(exc))
        if isinstance(exc, SQLAlchemyError):
            return ConnectorError(str(exc))
        return ConnectorError(str(exc))
