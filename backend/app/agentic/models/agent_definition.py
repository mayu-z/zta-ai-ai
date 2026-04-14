from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator, model_validator

from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, IntentClassification, RequestContext


TERMINAL_NODES = {
    "END",
    "END_SUCCESS",
    "END_FAILED",
    "END_CANCELLED",
    "END_NO_DATA",
    "END_PAID",
    "END_RATE_LIMITED",
    "END_NO_FEES",
    "END_DUPLICATE",
    "END_INELIGIBLE",
}


class AmbiguousEdge(Exception):
    pass


class FilterOperatorEnum(str, Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    LIKE = "like"
    IS_NULL = "is_null"


class NodeTypeEnum(str, Enum):
    FETCH = "fetch"
    ACTION = "action"
    CONDITION = "condition"
    LLM = "llm"
    RULE_EVAL = "rule_eval"
    NOTIFY = "notify"
    WRITE = "write"
    APPROVAL = "approval"
    EXTERNAL = "external"
    COMPUTE = "compute"
    WORKFLOW = "workflow"


class TriggerTypeEnum(str, Enum):
    USER_QUERY = "user_query"
    SCHEDULED = "scheduled"
    EVENT = "event"
    THRESHOLD = "threshold"
    ADMIN_INITIATED = "admin_initiated"


class TriggerDefinition(BaseModel):
    type: TriggerTypeEnum
    config: dict[str, Any] = Field(default_factory=dict)


class IntentDefinition(BaseModel):
    action_id: str | None = None
    classifier_hints: dict[str, Any] = Field(default_factory=dict)


class PolicyDefinition(BaseModel):
    allowed_personas: list[str] = Field(default_factory=list)
    required_data_scope: list[str] = Field(default_factory=list)
    requires_confirmation: bool | None = None
    human_approval_required: bool | None = None
    approval_level: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class PermissionsDefinition(BaseModel):
    allowed_personas: list[str]
    requires_confirmation: bool = True
    human_approval_required: bool = False
    approval_level: str | None = None


class DataScopeDefinition(BaseModel):
    required: list[str]
    has_sensitive_fields: bool = False
    cache_results: bool = True


class NodeDefinition(BaseModel):
    node_id: str
    type: NodeTypeEnum
    config: dict[str, Any] = Field(default_factory=dict)
    output_key: str | None = None

    @field_validator("node_id")
    @classmethod
    def no_spaces(cls, value: str) -> str:
        if " " in value:
            raise ValueError("node_id cannot contain spaces")
        return value.strip()


class EdgeDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: str = Field(alias="from")
    target: str = Field(alias="to")
    condition: str | None = None

    @field_validator("condition")
    @classmethod
    def validate_condition(cls, value: str | bool | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return "true" if value else "false"

        normalized = str(value).strip().lower()
        if normalized not in {"true", "false"}:
            raise ValueError("edge condition must be 'true', 'false', or null")
        return normalized


class AuditDefinition(BaseModel):
    log_fields: list[str] = Field(default_factory=list)
    hash_fields: list[str] = Field(default_factory=list)
    retention_days: int = 365


class MetadataDefinition(BaseModel):
    created_at: str = Field(default_factory=lambda: datetime.now(tz=UTC).date().isoformat())
    created_by: str = "engineering"
    tenant_overridable_fields: list[str] = Field(default_factory=list)
    migrated_from: str | None = None


class AgentDefinition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str
    display_name: str = ""
    version: str
    description: str = ""
    trigger: TriggerDefinition
    intent: IntentDefinition = Field(default_factory=IntentDefinition)
    policy: PolicyDefinition = Field(default_factory=PolicyDefinition)
    permissions: PermissionsDefinition = Field(default_factory=lambda: PermissionsDefinition(allowed_personas=[]))
    data_scope: DataScopeDefinition = Field(default_factory=lambda: DataScopeDefinition(required=[]))
    nodes: list[NodeDefinition] = Field(default_factory=list, alias="steps")
    edges: list[EdgeDefinition] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    audit: AuditDefinition = Field(default_factory=AuditDefinition)
    metadata: MetadataDefinition = Field(default_factory=MetadataDefinition)

    @field_validator("nodes")
    @classmethod
    def node_ids_unique(cls, nodes: list[NodeDefinition]) -> list[NodeDefinition]:
        ids = [node.node_id for node in nodes]
        duplicates = sorted({node_id for node_id in ids if ids.count(node_id) > 1})
        if duplicates:
            raise ValueError(f"Duplicate node IDs: {duplicates}")
        return nodes

    @field_validator("edges")
    @classmethod
    def edges_reference_valid_nodes(
        cls,
        edges: list[EdgeDefinition],
        info: ValidationInfo,
    ) -> list[EdgeDefinition]:
        nodes = info.data.get("nodes") if info.data else None
        if not nodes:
            return edges

        valid_ids = {node.node_id for node in nodes} | {"START"} | TERMINAL_NODES
        for edge in edges:
            if edge.source not in valid_ids:
                raise ValueError(f"Edge references unknown node: {edge.source}")
            if edge.target not in valid_ids:
                raise ValueError(f"Edge references unknown node: {edge.target}")
        return edges

    @model_validator(mode="after")
    def validate_graph(self) -> "AgentDefinition":
        # If edges are omitted, treat steps as an implicit linear flow.
        if not self.edges and self.nodes:
            generated: list[EdgeDefinition] = []
            generated.append(EdgeDefinition(source="START", target=self.nodes[0].node_id))
            for idx in range(0, len(self.nodes) - 1):
                generated.append(
                    EdgeDefinition(
                        source=self.nodes[idx].node_id,
                        target=self.nodes[idx + 1].node_id,
                    )
                )
            generated.append(EdgeDefinition(source=self.nodes[-1].node_id, target="END_SUCCESS"))
            self.edges = generated

        # Merge policy shortcuts into compatibility fields.
        if self.policy.allowed_personas and not self.permissions.allowed_personas:
            self.permissions.allowed_personas = list(self.policy.allowed_personas)
        if self.policy.required_data_scope and not self.data_scope.required:
            self.data_scope.required = list(self.policy.required_data_scope)
        if self.policy.requires_confirmation is not None:
            self.permissions.requires_confirmation = bool(self.policy.requires_confirmation)
        if self.policy.human_approval_required is not None:
            self.permissions.human_approval_required = bool(self.policy.human_approval_required)
        if self.policy.approval_level:
            self.permissions.approval_level = self.policy.approval_level

        adjacency: dict[str, list[str]] = {}
        for edge in self.edges:
            adjacency.setdefault(edge.source, []).append(edge.target)
            if edge.source in TERMINAL_NODES:
                raise ValueError(f"Terminal node '{edge.source}' cannot have outgoing edges")

        # Validate at least one path from START to a terminal node.
        reachable = set()
        stack = ["START"]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for nxt in adjacency.get(current, []):
                if nxt not in reachable:
                    stack.append(nxt)

        terminals_reached = TERMINAL_NODES.intersection(reachable)
        if not terminals_reached and self.edges:
            raise ValueError("Graph must have a reachable terminal node from START")

        # Cycle detection among non-terminal nodes.
        state: dict[str, int] = {}

        def visit(node_id: str) -> bool:
            if node_id in TERMINAL_NODES:
                return False
            marker = state.get(node_id, 0)
            if marker == 1:
                return True
            if marker == 2:
                return False

            state[node_id] = 1
            for child in adjacency.get(node_id, []):
                if visit(child):
                    return True
            state[node_id] = 2
            return False

        for node_id in ["START", *[node.node_id for node in self.nodes]]:
            if visit(node_id):
                raise ValueError("Circular graph references are not allowed")

        return self

    @property
    def steps(self) -> list[NodeDefinition]:
        return self.nodes

    def get_node(self, node_id: str) -> NodeDefinition | None:
        return next((node for node in self.nodes if node.node_id == node_id), None)

    def resolve_next(self, current_node_id: str, condition_value: bool | None = None) -> str:
        matching = [
            edge
            for edge in self.edges
            if edge.source == current_node_id
            and (
                edge.condition is None
                or (edge.condition == "true" and condition_value is True)
                or (edge.condition == "false" and condition_value is False)
            )
        ]

        if not matching:
            return "END"

        if len(matching) > 1:
            raise AmbiguousEdge(f"Ambiguous outgoing edges from '{current_node_id}'")

        return matching[0].target


class ExecutionContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    intent: IntentClassification
    ctx: RequestContext
    definition: AgentDefinition
    claim_sets: dict[str, ClaimSet] = Field(default_factory=dict)
    computed_values: dict[str, Any] = Field(default_factory=dict)
    workflow_id: str | None = None

    def store(self, key: str, value: Any) -> None:
        self.computed_values[key] = value

    def resolve(self, template_value: str) -> Any:
        if not isinstance(template_value, str):
            return template_value

        full_ref = re.match(r"^\s*\{\{\s*([^{}]+)\s*\}\}\s*$", template_value)
        if full_ref:
            return self._resolve_path(full_ref.group(1).strip())

        token_pattern = re.compile(r"\{\{\s*([^{}]+)\s*\}\}")

        def _replace(match: re.Match[str]) -> str:
            resolved = self._resolve_path(match.group(1).strip())
            if resolved is None:
                return ""
            return str(resolved)

        return token_pattern.sub(_replace, template_value)

    def _resolve_path(self, key_path: str) -> Any:
        obj: Any = {
            **self.claim_sets,
            **self.computed_values,
            "ctx": self.ctx,
            "intent": self.intent,
        }

        for key in key_path.split("."):
            token = key.strip()
            if not token:
                continue

            if isinstance(obj, dict):
                obj = obj.get(token)
            elif isinstance(obj, (list, tuple)) and token.isdigit():
                idx = int(token)
                obj = obj[idx] if 0 <= idx < len(obj) else None
            else:
                obj = getattr(obj, token, None)

            if obj is None:
                return None

        return obj

    def build_result(self) -> AgentResult:
        status_raw = self.computed_values.get("_final_status", AgentStatus.SUCCESS)
        if isinstance(status_raw, AgentStatus):
            status = status_raw
        else:
            try:
                status = AgentStatus(str(status_raw))
            except ValueError:
                status = AgentStatus.FAILED

        message = str(self.computed_values.get("_final_message", "Action completed."))
        result_data = self.computed_values.get("_result_data")
        return AgentResult(
            status=status,
            message=message,
            workflow_id=self.workflow_id,
            data=result_data,
        )


class NodeResult(BaseModel):
    output: Any = None
    condition_value: bool | None = None
    should_halt: bool = False
    halt_status: AgentStatus | None = None
    halt_message: str | None = None
