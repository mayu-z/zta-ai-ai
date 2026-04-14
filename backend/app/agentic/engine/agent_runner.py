from __future__ import annotations

import hashlib
from typing import Any

from app.agentic.engine.node_executor import NodeExecutor, UnknownNodeType
from app.agentic.models.agent_context import AgentResult, AgentStatus, IntentClassification, RequestContext
from app.agentic.models.agent_definition import AgentDefinition, AmbiguousEdge, ExecutionContext, TERMINAL_NODES
from app.agentic.models.audit_event import AuditEvent
from app.agentic.registry.agent_registry import AgentDefinitionLoader


TERMINAL_STATUS_MAP: dict[str, AgentStatus] = {
    "END": AgentStatus.SUCCESS,
    "END_SUCCESS": AgentStatus.SUCCESS,
    "END_FAILED": AgentStatus.FAILED,
    "END_CANCELLED": AgentStatus.CANCELLED,
    "END_NO_DATA": AgentStatus.SUCCESS,
    "END_PAID": AgentStatus.SUCCESS,
    "END_RATE_LIMITED": AgentStatus.SUCCESS,
    "END_NO_FEES": AgentStatus.SUCCESS,
    "END_DUPLICATE": AgentStatus.FAILED,
    "END_INELIGIBLE": AgentStatus.FAILED,
}


class AgentRunner:
    def __init__(
        self,
        *,
        definition_loader: AgentDefinitionLoader,
        node_executor: NodeExecutor,
        action_registry: Any,
        policy_engine: Any,
        audit_logger: Any,
    ):
        self._loader = definition_loader
        self._executor = node_executor
        self._registry = action_registry
        self._policy = policy_engine
        self._audit = audit_logger

    async def run(self, *, agent_id: str, intent: IntentClassification, ctx: RequestContext) -> AgentResult:
        definition = await self._loader.load(agent_id, ctx.tenant_id)
        if definition is None:
            return AgentResult(status=AgentStatus.FALLBACK_TO_INFO, message="No matching action found.")
        return await self.execute_agent(definition, intent=intent, ctx=ctx)

    async def execute_agent(
        self,
        agent_json: AgentDefinition | dict[str, Any],
        *,
        intent: IntentClassification,
        ctx: RequestContext,
    ) -> AgentResult:
        definition = (
            agent_json if isinstance(agent_json, AgentDefinition) else AgentDefinition.model_validate(agent_json)
        )

        action_id = intent.action_id or definition.intent.action_id or definition.agent_id
        if not action_id:
            return AgentResult(status=AgentStatus.FAILED, message="Action id is missing")

        action = await self._registry.get(action_id, ctx.tenant_id)
        if action is None or not action.is_enabled:
            return AgentResult(status=AgentStatus.FALLBACK_TO_INFO, message="No matching action found.")

        policy_decision = await self._policy.evaluate(action, ctx)
        if not policy_decision.allowed:
            return AgentResult(
                status=AgentStatus.PERMISSION_DENIED,
                message=policy_decision.denial_reason or "Permission denied",
            )

        exec_ctx = ExecutionContext(intent=intent, ctx=ctx, definition=definition)
        steps_executed: list[dict[str, Any]] = []
        actions_triggered: list[str] = []
        current_node_id = "START"
        terminal_node = "END"
        result = AgentResult(status=AgentStatus.FAILED, message="Execution error")
        seen_edges: set[str] = set()

        try:
            while True:
                if current_node_id in TERMINAL_NODES:
                    terminal_node = current_node_id
                    status = TERMINAL_STATUS_MAP.get(current_node_id, AgentStatus.SUCCESS)
                    exec_ctx.store("_final_status", status)
                    if "_final_message" not in exec_ctx.computed_values:
                        exec_ctx.store("_final_message", f"Completed at {current_node_id}")
                    break

                if current_node_id == "START":
                    next_node_id, edge_key = self._resolve_edge(definition, "START", None)
                    if edge_key:
                        self._mark_edge(edge_key, seen_edges)
                    current_node_id = next_node_id
                    continue

                node = definition.get_node(current_node_id)
                if node is None:
                    exec_ctx.store("_final_status", AgentStatus.FAILED)
                    exec_ctx.store("_final_message", f"Unknown node '{current_node_id}'")
                    terminal_node = "END_FAILED"
                    break

                node_result = await self._executor.execute(node, exec_ctx)

                if node.output_key:
                    if hasattr(node_result.output, "claims") and hasattr(node_result.output, "row_count"):
                        exec_ctx.claim_sets[node.output_key] = node_result.output
                    else:
                        exec_ctx.store(node.output_key, node_result.output)
                elif node_result.output is not None:
                    exec_ctx.store(node.node_id, node_result.output)

                if str(node.type.value if hasattr(node.type, "value") else node.type) == "action":
                    action_info = node_result.output if isinstance(node_result.output, dict) else {}
                    action_name = str(action_info.get("action_id") or action_id)
                    actions_triggered.append(action_name)

                steps_executed.append(
                    {
                        "node_id": node.node_id,
                        "type": str(node.type.value if hasattr(node.type, "value") else node.type),
                        "halted": bool(node_result.should_halt),
                    }
                )

                if node_result.should_halt:
                    exec_ctx.store("_final_status", node_result.halt_status or AgentStatus.FAILED)
                    exec_ctx.store("_final_message", node_result.halt_message or "Execution halted")
                    terminal_node = "END_CANCELLED"
                    break

                next_node_id, edge_key = self._resolve_edge(definition, node.node_id, node_result.condition_value)
                if edge_key:
                    self._mark_edge(edge_key, seen_edges)
                current_node_id = next_node_id

            result = exec_ctx.build_result()
            payload = dict(result.data or {})
            payload.setdefault("steps_executed", steps_executed)
            payload.setdefault("actions_triggered", actions_triggered)
            result.data = payload
            return result

        except UnknownNodeType as exc:
            result = AgentResult(status=AgentStatus.FAILED, message=str(exc))
            return result
        except AmbiguousEdge as exc:
            result = AgentResult(status=AgentStatus.FAILED, message=str(exc))
            return result
        except Exception as exc:  # noqa: BLE001
            result = AgentResult(status=AgentStatus.FAILED, message=f"Execution error: {type(exc).__name__}")
            return result
        finally:
            payload_hash = None
            if result.data is not None:
                payload_hash = hashlib.sha256(str(result.data).encode("utf-8")).hexdigest()

            await self._audit.write(
                AuditEvent(
                    event_type="JSON_AGENTIC_ACTION",
                    action_id=action_id,
                    user_alias=ctx.user_alias,
                    tenant_id=ctx.tenant_id,
                    status=result.status.value,
                    payload_hash=payload_hash,
                    metadata={
                        "agent_id": definition.agent_id,
                        "terminal_node": terminal_node,
                        "steps_executed": steps_executed,
                        "actions_triggered": actions_triggered,
                    },
                )
            )

    @staticmethod
    def _resolve_edge(
        definition: AgentDefinition,
        source: str,
        condition_value: bool | None,
    ) -> tuple[str, str | None]:
        matching = [
            edge
            for edge in definition.edges
            if edge.source == source
            and (
                edge.condition is None
                or (edge.condition == "true" and condition_value is True)
                or (edge.condition == "false" and condition_value is False)
            )
        ]
        if not matching:
            return "END", None
        if len(matching) > 1:
            raise AmbiguousEdge(f"Ambiguous outgoing edges from '{source}'")

        edge = matching[0]
        edge_key = f"{edge.source}->{edge.target}:{edge.condition or 'any'}"
        return edge.target, edge_key

    @staticmethod
    def _mark_edge(edge_key: str, seen_edges: set[str]) -> None:
        if edge_key in seen_edges:
            raise RuntimeError(f"Graph attempted to traverse edge twice: {edge_key}")
        seen_edges.add(edge_key)
