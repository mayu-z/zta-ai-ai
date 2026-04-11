from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.source_types import LOCAL_STORE_SOURCE_TYPES
from app.core.config import get_settings as _get_settings
from app.core.exceptions import ValidationError
from app.db.models import (
    ControlGraphEdge,
    ControlGraphNode,
    DataSource,
    DataSourceStatus,
    DataSourceType,
    DomainSourceBinding,
)

from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, ScopeContext


_BROADCAST_SCOPE_DOMAINS = {"notices", "campus"}


class QueryBuilder:
    def build(
        self,
        scope: ScopeContext,
        intent: InterpretedIntent,
        db: Session | None = None,
    ) -> CompiledQueryPlan:
        slot_map = {f"SLOT_{idx + 1}": key for idx, key in enumerate(intent.slot_keys)}

        if db is not None and self._has_control_graph(db=db, tenant_id=scope.tenant_id):
            self._validate_domain_and_slots_with_graph(
                db=db,
                tenant_id=scope.tenant_id,
                intent=intent,
            )

        filters: dict[str, object] = {
            "tenant_id": scope.tenant_id,
            "domain": intent.domain,
            "entity_type": intent.entity_type,
        }

        broadcast_scope = intent.domain in _BROADCAST_SCOPE_DOMAINS

        # Preferred path: runtime-configured row scope filters.
        applied_scope = False
        if not broadcast_scope:
            for key, value in scope.row_scope_filters.items():
                if value is None:
                    continue
                if isinstance(value, list) and not value:
                    continue
                filters[key] = value
                applied_scope = True

        # Legacy fallback to preserve existing behavior for tokens without row scope.
        if not applied_scope and not broadcast_scope:
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

        if self._has_control_graph(db=db, tenant_id=tenant_id):
            graph_source = self._resolve_source_from_graph(
                db=db,
                tenant_id=tenant_id,
                domain=domain,
            )
            if graph_source is not None:
                return graph_source

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

    def _has_control_graph(self, db: Session, tenant_id: str) -> bool:
        return (
            db.scalar(
                select(ControlGraphNode.id).where(
                    ControlGraphNode.tenant_id == tenant_id
                )
            )
            is not None
        )

    def _validate_domain_and_slots_with_graph(
        self,
        *,
        db: Session,
        tenant_id: str,
        intent: InterpretedIntent,
    ) -> None:
        domain_node = db.scalar(
            select(ControlGraphNode).where(
                ControlGraphNode.tenant_id == tenant_id,
                ControlGraphNode.node_type == "domain",
                ControlGraphNode.node_key == intent.domain,
            )
        )
        if domain_node is None:
            raise ValidationError(
                message="Detected domain is not mapped in control graph",
                code="GRAPH_DOMAIN_NOT_MAPPED",
            )

        intent_node = db.scalar(
            select(ControlGraphNode).where(
                ControlGraphNode.tenant_id == tenant_id,
                ControlGraphNode.node_type == "intent",
                ControlGraphNode.node_key == intent.name,
            )
        )
        if intent_node is None:
            raise ValidationError(
                message="Resolved intent is not mapped in control graph",
                code="GRAPH_INTENT_NOT_MAPPED",
            )

        edge_exists = (
            db.scalar(
                select(ControlGraphEdge.id).where(
                    ControlGraphEdge.tenant_id == tenant_id,
                    ControlGraphEdge.edge_type == "intent_targets_domain",
                    ControlGraphEdge.source_node_id == intent_node.id,
                    ControlGraphEdge.target_node_id == domain_node.id,
                )
            )
            is not None
        )
        if not edge_exists:
            raise ValidationError(
                message="Intent-domain mapping is inconsistent in control graph",
                code="GRAPH_INTENT_DOMAIN_MISMATCH",
            )

        intent_attributes = (
            intent_node.attributes if isinstance(intent_node.attributes, dict) else {}
        )
        allowed_slots_raw = intent_attributes.get("slot_keys")
        if isinstance(allowed_slots_raw, list) and allowed_slots_raw:
            allowed_slots = {
                str(item).strip()
                for item in allowed_slots_raw
                if str(item).strip()
            }
            invalid_slots = [
                slot for slot in intent.slot_keys if slot not in allowed_slots
            ]
            if invalid_slots:
                raise ValidationError(
                    message="Intent slot keys are not permitted by control graph",
                    code="GRAPH_SLOT_KEY_MISMATCH",
                )

    def _resolve_source_from_graph(
        self,
        *,
        db: Session,
        tenant_id: str,
        domain: str,
    ) -> tuple[str, str | None, str | None] | None:
        domain_node = db.scalar(
            select(ControlGraphNode).where(
                ControlGraphNode.tenant_id == tenant_id,
                ControlGraphNode.node_type == "domain",
                ControlGraphNode.node_key == domain,
            )
        )
        if domain_node is None:
            return None

        edges = db.scalars(
            select(ControlGraphEdge).where(
                ControlGraphEdge.tenant_id == tenant_id,
                ControlGraphEdge.edge_type == "domain_bound_to_source",
                ControlGraphEdge.source_node_id == domain_node.id,
            )
        ).all()
        if not edges:
            return None

        selected_edge = None
        for edge in edges:
            attributes = edge.attributes if isinstance(edge.attributes, dict) else {}
            if bool(attributes.get("is_active", True)):
                selected_edge = edge
                break
        if selected_edge is None:
            selected_edge = edges[0]

        target_node = db.scalar(
            select(ControlGraphNode).where(
                ControlGraphNode.tenant_id == tenant_id,
                ControlGraphNode.id == selected_edge.target_node_id,
            )
        )
        if target_node is None:
            raise ValidationError(
                message="Control graph source target node is missing",
                code="GRAPH_SOURCE_TARGET_MISSING",
            )

        edge_attributes = (
            selected_edge.attributes
            if isinstance(selected_edge.attributes, dict)
            else {}
        )
        binding_id_raw = edge_attributes.get("binding_id")
        source_binding_id = str(binding_id_raw).strip() if binding_id_raw else None

        if target_node.node_type == "data_source":
            data_source_id = target_node.node_key.strip()
            source = db.scalar(
                select(DataSource).where(
                    DataSource.id == data_source_id,
                    DataSource.tenant_id == tenant_id,
                )
            )
            if not source:
                raise ValidationError(
                    message="Control graph references a missing data source",
                    code="GRAPH_SOURCE_NOT_FOUND",
                )
            if source.status != DataSourceStatus.connected:
                raise ValidationError(
                    message="Control graph references a disconnected data source",
                    code="GRAPH_SOURCE_NOT_CONNECTED",
                )
            return source.source_type.value, source.id, source_binding_id

        if target_node.node_type == "source_type":
            source_type = target_node.node_key.strip().lower()
            allowed_source_types = {item.value for item in DataSourceType}
            if source_type not in allowed_source_types:
                raise ValidationError(
                    message="Control graph source type is invalid",
                    code="GRAPH_SOURCE_TYPE_INVALID",
                )
            return source_type, None, source_binding_id

        raise ValidationError(
            message="Control graph source target type is unsupported",
            code="GRAPH_SOURCE_TARGET_INVALID",
        )

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
