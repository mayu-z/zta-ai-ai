from __future__ import annotations

import asyncio
from dataclasses import dataclass
import base64
import json
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agentic.models.execution_plan import QueryFilter, ReadExecutionPlan, WriteExecutionPlan
from app.db.models import DataSource, DataSourceStatus, DomainSourceBinding
from app.db.session import SessionLocal

from .base import ConnectorError, RawResult, WriteResult
from .registry import ConnectorPool


@dataclass(frozen=True)
class SourceConfig:
    source_type: str
    source_id: str
    entity_mapping: str
    field_mappings: dict[str, str]
    connection_config: dict[str, Any]


class TenantConfigService:
    """Fetches entity-to-source connector mappings for a tenant."""

    async def get_source_for_entity(self, *, entity: str, tenant_id: UUID) -> SourceConfig | None:
        return await asyncio.to_thread(self._get_source_for_entity_sync, entity, tenant_id)

    def _get_source_for_entity_sync(self, entity: str, tenant_id: UUID) -> SourceConfig | None:
        db = SessionLocal()
        try:
            binding = db.scalar(
                select(DomainSourceBinding)
                .where(DomainSourceBinding.tenant_id == str(tenant_id))
                .where(DomainSourceBinding.domain == entity)
                .where(DomainSourceBinding.is_active.is_(True))
            )

            if binding is None or not binding.data_source_id:
                return None

            data_source = db.scalar(
                select(DataSource)
                .where(DataSource.id == binding.data_source_id)
                .where(DataSource.tenant_id == str(tenant_id))
                .where(DataSource.status == DataSourceStatus.connected)
            )

            if data_source is None:
                return None

            source_payload = self._decode_config(data_source.config_encrypted)
            source_type = self._normalize_source_type(data_source.source_type.value)

            entity_mapping = self._resolve_entity_mapping(entity=entity, payload=source_payload)
            field_mappings = self._resolve_field_mappings(entity=entity, payload=source_payload)
            return SourceConfig(
                source_type=source_type,
                source_id=data_source.id,
                entity_mapping=entity_mapping,
                field_mappings=field_mappings,
                connection_config=source_payload,
            )
        finally:
            db.close()

    def _decode_config(self, raw: str) -> dict[str, Any]:
        payload_raw = (raw or "").strip()
        if not payload_raw:
            return {}
        try:
            decoded = base64.b64decode(payload_raw).decode("utf-8")
            payload = json.loads(decoded)
            if isinstance(payload, dict):
                return payload
            return {}
        except Exception:
            return {}

    def _resolve_entity_mapping(self, *, entity: str, payload: dict[str, Any]) -> str:
        mappings = payload.get("entity_mappings")
        if isinstance(mappings, dict):
            mapped = mappings.get(entity)
            if isinstance(mapped, str) and mapped.strip():
                return mapped.strip()

        fallback = payload.get("entity_mapping")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()
        return entity

    def _resolve_field_mappings(self, *, entity: str, payload: dict[str, Any]) -> dict[str, str]:
        mappings = payload.get("field_mappings")
        if isinstance(mappings, dict):
            nested = mappings.get(entity)
            if isinstance(nested, dict):
                return {str(k): str(v) for k, v in nested.items()}

        flat = payload.get("field_map")
        if isinstance(flat, dict):
            return {str(k): str(v) for k, v in flat.items()}

        return {}

    def _normalize_source_type(self, source_type: str) -> str:
        normalized = str(source_type).strip().lower()
        if normalized == "postgresql":
            return "postgres"
        return normalized


class ConnectorRouter:
    def __init__(self, pool: ConnectorPool, tenant_config_service: TenantConfigService):
        self._pool = pool
        self._config = tenant_config_service

    async def route_read(self, plan: ReadExecutionPlan, tenant_id: UUID) -> RawResult:
        source_config = await self._config.get_source_for_entity(entity=plan.entity, tenant_id=tenant_id)
        if source_config is None:
            raise ConnectorError(f"No data source configured for entity '{plan.entity}'")

        translated_plan = self._translate_read_plan(plan, source_config)
        connector = await self._pool.get(
            tenant_id=tenant_id,
            source_type=source_config.source_type,
            source_id=source_config.source_id,
            config=source_config.connection_config,
        )
        return await connector.execute(translated_plan)

    async def route_write(self, plan: WriteExecutionPlan, tenant_id: UUID) -> WriteResult:
        source_config = await self._config.get_source_for_entity(entity=plan.entity, tenant_id=tenant_id)
        if source_config is None:
            raise ConnectorError(f"No data source configured for entity '{plan.entity}'")

        translated_plan = self._translate_write_plan(plan, source_config)
        connector = await self._pool.get(
            tenant_id=tenant_id,
            source_type=source_config.source_type,
            source_id=source_config.source_id,
            config=source_config.connection_config,
        )
        return await connector.write(translated_plan)

    def _translate_read_plan(self, plan: ReadExecutionPlan, source_config: SourceConfig) -> ReadExecutionPlan:
        translated_fields = [source_config.field_mappings.get(field, field) for field in plan.fields]
        translated_filters = [
            QueryFilter(
                field=source_config.field_mappings.get(item.field, item.field),
                operator=item.operator,
                value=item.value,
            )
            for item in plan.filters
        ]
        translated_order = source_config.field_mappings.get(plan.order_by, plan.order_by) if plan.order_by else None
        return ReadExecutionPlan(
            plan_id=plan.plan_id,
            entity=source_config.entity_mapping,
            action_id=plan.action_id,
            fields=translated_fields,
            filters=translated_filters,
            scope=plan.scope,
            operation=plan.operation,
            payload=dict(plan.payload),
            order_by=translated_order,
            limit=plan.limit,
            offset=plan.offset,
            scope_filters_required=plan.scope_filters_required,
        )

    def _translate_write_plan(self, plan: WriteExecutionPlan, source_config: SourceConfig) -> WriteExecutionPlan:
        translated_payload = {
            source_config.field_mappings.get(field, field): value
            for field, value in plan.payload.items()
        }
        translated_filters = [
            QueryFilter(
                field=source_config.field_mappings.get(item.field, item.field),
                operator=item.operator,
                value=item.value,
            )
            for item in plan.filters
        ]
        return WriteExecutionPlan(
            plan_id=plan.plan_id,
            entity=source_config.entity_mapping,
            operation=plan.operation,
            payload=translated_payload,
            action_id=plan.action_id,
            filters=translated_filters,
            scope=plan.scope,
            allowed_by_action_id=plan.allowed_by_action_id,
            scope_filters_required=plan.scope_filters_required,
        )
