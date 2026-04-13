from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal


class FilterOperator(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    LIKE = "like"
    IS_NULL = "is_null"


@dataclass(frozen=True)
class ScopeFilter:
    """Mandatory scope constraints injected by the scope injector."""

    tenant_id: str
    user_alias: str | None
    department_id: str | None


@dataclass(frozen=True)
class QueryFilter:
    field: str
    operator: FilterOperator = FilterOperator.EQ
    value: Any = None


@dataclass(frozen=True)
class ReadExecutionPlan:
    plan_id: str
    entity: str
    action_id: str = ""
    fields: list[str] = field(default_factory=list)
    filters: list[QueryFilter] = field(default_factory=list)
    scope: ScopeFilter = field(
        default_factory=lambda: ScopeFilter(tenant_id="", user_alias=None, department_id=None)
    )
    operation: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    order_by: str | None = None
    limit: int = 100
    offset: int = 0
    scope_filters_required: bool = False


@dataclass(frozen=True)
class WriteExecutionPlan:
    plan_id: str
    entity: str
    operation: Literal["INSERT", "UPDATE", "DELETE", "create_event", "send_email", "create_link"]
    payload: dict[str, Any]
    action_id: str = ""
    filters: list[QueryFilter] = field(default_factory=list)
    scope: ScopeFilter = field(
        default_factory=lambda: ScopeFilter(tenant_id="", user_alias=None, department_id=None)
    )
    allowed_by_action_id: str = ""
    scope_filters_required: bool = False


@dataclass(frozen=True)
class ExternalServicePlan:
    plan_id: str
    service_type: str
    operation: str
    payload: dict[str, Any]
    scope: ScopeFilter
    tenant_id: str
