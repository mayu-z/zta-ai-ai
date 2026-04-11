from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.source_types import LOCAL_STORE_SOURCE_TYPES
from app.core.config import get_settings as _get_settings
from app.core.exceptions import ValidationError
from app.db.models import DataSource, DataSourceStatus, DomainSourceBinding

from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, ScopeContext


class QueryBuilder:
    def build(
        self,
        scope: ScopeContext,
        intent: InterpretedIntent,
        db: Session | None = None,
    ) -> CompiledQueryPlan:
        slot_map = {f"SLOT_{idx + 1}": key for idx, key in enumerate(intent.slot_keys)}

        filters: dict[str, object] = {
            "tenant_id": scope.tenant_id,
            "domain": intent.domain,
            "entity_type": intent.entity_type,
        }

        # Preferred path: runtime-configured row scope filters.
        applied_scope = False
        for key, value in scope.row_scope_filters.items():
            if value is None:
                continue
            if isinstance(value, list) and not value:
                continue
            filters[key] = value
            applied_scope = True

        # Legacy fallback to preserve existing behavior for tokens without row scope.
        if not applied_scope:
            if scope.persona_type == "student":
                filters["owner_id"] = scope.own_id
            elif scope.persona_type == "faculty":
                filters["course_ids"] = scope.course_ids
            elif scope.persona_type == "dept_head":
                filters["department_id"] = scope.department
            elif scope.persona_type == "admin_staff":
                filters["admin_function"] = scope.admin_function

        if scope.aggregate_only:
            filters["aggregate_only"] = True

        for key, value in intent.filters.items():
            filters[key] = value

        signature_parts = [
            "tenant_id=:tenant_id",
            "domain=:domain",
            "entity_type=:entity_type",
        ]
        if "owner_id" in filters:
            signature_parts.append("owner_id=:owner_id")
        if "department_id" in filters:
            signature_parts.append("department_id=:department_id")
        if "admin_function" in filters:
            signature_parts.append("admin_function=:admin_function")
        if "course_ids" in filters:
            signature_parts.append("course_id IN (:course_ids)")

        source_type, data_source_id, source_binding_id = self._resolve_source(
            db=db,
            tenant_id=scope.tenant_id,
            domain=intent.domain,
        )
        signature_parts.append("source_type=:source_type")
        if data_source_id:
            signature_parts.append("data_source_id=:data_source_id")

        return CompiledQueryPlan(
            tenant_id=scope.tenant_id,
            source_type=source_type,
            data_source_id=data_source_id,
            source_binding_id=source_binding_id,
            domain=intent.domain,
            entity_type=intent.entity_type,
            select_keys=intent.slot_keys,
            select_claim_keys=intent.slot_keys,
            filters=filters,
            slot_map=slot_map,
            requires_aggregate=scope.aggregate_only
            or bool(intent.aggregation == "aggregate"),
            parameterized_signature=" AND ".join(signature_parts),
        )

    def _resolve_source(
        self,
        db: Session | None,
        tenant_id: str,
        domain: str,
    ) -> tuple[str, str | None, str | None]:
        fallback_source = self._fallback_source_type(tenant_id)
        if db is None:
            return fallback_source, None, None

        binding = db.scalar(
            select(DomainSourceBinding).where(
                DomainSourceBinding.tenant_id == tenant_id,
                DomainSourceBinding.domain == domain,
                DomainSourceBinding.is_active.is_(True),
            )
        )
        if not binding:
            return fallback_source, None, None

        source_type = binding.source_type.value
        data_source_id = binding.data_source_id
        if data_source_id:
            source = db.scalar(
                select(DataSource).where(
                    DataSource.id == data_source_id,
                    DataSource.tenant_id == tenant_id,
                )
            )
            if not source:
                raise ValidationError(
                    message="Domain source binding references a missing data source",
                    code="BOUND_SOURCE_NOT_FOUND",
                )
            if source.status != DataSourceStatus.connected:
                raise ValidationError(
                    message="Domain source binding points to a disconnected source",
                    code="BOUND_SOURCE_NOT_CONNECTED",
                )
            source_type = source.source_type.value

        return source_type, data_source_id, binding.id

    def _fallback_source_type(self, tenant_id: str) -> str:
        _ = tenant_id  # kept for signature stability
        configured = _get_settings().default_local_source_type.strip().lower()
        if configured not in LOCAL_STORE_SOURCE_TYPES:
            raise ValidationError(
                message="Configured default_local_source_type is not supported",
                code="DEFAULT_SOURCE_TYPE_INVALID",
            )
        return configured


query_builder = QueryBuilder()
