from __future__ import annotations

from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import RequestContext
from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ScopeFilter


class ScopeInjector:
    SCOPE_FILTER_MAP: dict[str, dict[str, str]] = {
        "fees.own": {"field": "student_id", "value_from": "user_alias"},
        "attendance.own": {"field": "student_id", "value_from": "user_alias"},
        "payroll.own": {"field": "employee_id", "value_from": "user_alias"},
        "hr.own": {"field": "employee_id", "value_from": "user_alias"},
        "results.own": {"field": "student_id", "value_from": "user_alias"},
        "leave_records.own": {"field": "employee_id", "value_from": "user_alias"},
        "user_directory.dept": {"field": "department_id", "value_from": "department_id"},
        "user_directory.department_scope": {"field": "department_id", "value_from": "department_id"},
        "calendar.own": {"field": "user_alias", "value_from": "user_alias"},
        "calendar.participants": {"field": "department_id", "value_from": "department_id"},
    }

    def inject(
        self,
        action: ActionConfig,
        ctx: RequestContext,
        entity: str,
    ) -> tuple[ScopeFilter, list[QueryFilter]]:
        scope = ScopeFilter(
            tenant_id=str(ctx.tenant_id),
            user_alias=ctx.user_alias,
            department_id=ctx.department_id,
        )

        additional_filters: list[QueryFilter] = []
        for descriptor in action.required_data_scope:
            if not self._matches_entity(descriptor, entity):
                continue

            mapping = self._resolve_mapping(descriptor)
            if mapping is None:
                continue

            value = getattr(ctx, mapping["value_from"], None)
            if value is None or value == "":
                continue

            additional_filters.append(
                QueryFilter(
                    field=mapping["field"],
                    operator=FilterOperator.EQ,
                    value=value,
                )
            )

        return scope, self._dedupe_filters(additional_filters)

    def _resolve_mapping(self, descriptor: str) -> dict[str, str] | None:
        normalized = descriptor.strip().lower()
        if normalized in self.SCOPE_FILTER_MAP:
            return self.SCOPE_FILTER_MAP[normalized]

        # Descriptors can contain suffixes like "calendar.own.free_busy".
        parts = normalized.split(".")
        while len(parts) > 1:
            parts.pop()
            prefix = ".".join(parts)
            if prefix in self.SCOPE_FILTER_MAP:
                return self.SCOPE_FILTER_MAP[prefix]
        return None

    def _matches_entity(self, descriptor: str, entity: str) -> bool:
        return descriptor.strip().lower().split(".", 1)[0] == entity.strip().lower()

    def _dedupe_filters(self, filters: list[QueryFilter]) -> list[QueryFilter]:
        seen: set[tuple[str, str, str]] = set()
        deduped: list[QueryFilter] = []
        for item in filters:
            key = (item.field, item.operator.value, str(item.value))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped
