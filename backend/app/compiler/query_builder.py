from __future__ import annotations

from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, ScopeContext


class QueryBuilder:
    def build(self, scope: ScopeContext, intent: InterpretedIntent) -> CompiledQueryPlan:
        slot_map = {f"SLOT_{idx + 1}": key for idx, key in enumerate(intent.slot_keys)}

        filters: dict[str, object] = {
            "tenant_id": scope.tenant_id,
            "domain": intent.domain,
            "entity_type": intent.entity_type,
        }

        # Mandatory persona scope injection (compiler authority).
        if scope.persona_type == "student":
            filters["owner_id"] = scope.own_id
        elif scope.persona_type == "faculty":
            filters["course_ids"] = scope.course_ids
        elif scope.persona_type == "dept_head":
            filters["department_id"] = scope.department
        elif scope.persona_type == "admin_staff":
            filters["admin_function"] = scope.admin_function
        elif scope.persona_type == "executive":
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

        return CompiledQueryPlan(
            tenant_id=scope.tenant_id,
            source_type="mock_claims",
            domain=intent.domain,
            entity_type=intent.entity_type,
            select_claim_keys=intent.slot_keys,
            filters=filters,
            slot_map=slot_map,
            requires_aggregate=scope.aggregate_only or bool(intent.aggregation == "aggregate"),
            parameterized_signature=" AND ".join(signature_parts),
        )


query_builder = QueryBuilder()
