import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.executor import AgentExecutor
from app.api.dependencies import (
    get_agent_executor,
    get_intent_resolver,
    get_orchestrator,
    get_registry_service,
)
from app.schemas.execution import ConfirmRequest, ExecuteRequest, ExecutionResult
from app.services.intent_resolver import IntentResolver
from app.services.orchestrator import ExecutionOrchestrator
from app.services.registry_service import RegistryService

router = APIRouter(tags=["execution"])
logger = logging.getLogger(__name__)


@router.post("/execute", summary="Execute agent from user query")
async def execute(
    request: ExecuteRequest,
    registry: RegistryService = Depends(get_registry_service),
    resolver: IntentResolver = Depends(get_intent_resolver),
    agent_executor: AgentExecutor = Depends(get_agent_executor),
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> ExecutionResult:
    logger.info(
        "execute.request_received",
        extra={
            "tenant_id": request.tenant_id,
            "persona": request.user_context.persona,
            "query": request.query,
            "user_id": request.user_context.user_id,
        },
    )
    try:
        enabled_agents = registry.list_enabled_agents(
            tenant_id=request.tenant_id,
            persona_type=request.user_context.persona,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    logger.info(
        "execute.enabled_agents_resolved",
        extra={
            "tenant_id": request.tenant_id,
            "persona": request.user_context.persona,
            "enabled_agent_count": len(enabled_agents),
            "enabled_agent_ids": [candidate.get("agent_id") for candidate in enabled_agents],
        },
    )

    try:
        leave_balance_diag = registry.debug_agent_runtime_snapshot(
            tenant_id=request.tenant_id,
            persona_type=request.user_context.persona,
            agent_id="leave_balance_v1",
        )
        logger.info("execute.registry_leave_balance_diagnostic", extra=leave_balance_diag)
    except Exception as exc:  # pragma: no cover - diagnostics must never block execution
        logger.warning(
            "execute.registry_leave_balance_diagnostic_failed",
            extra={"tenant_id": request.tenant_id, "error": str(exc)},
        )

    if not enabled_agents:
        logger.info(
            "execute.branch_no_enabled_agents",
            extra={"tenant_id": request.tenant_id, "persona": request.user_context.persona},
        )
        return ExecutionResult(
            execution_id="",
            status="failed",
            state="FAILED",
            output_summary="No enabled agents available for this persona",
        )

    resolution = resolver.resolve(
        query_text=request.query,
        tenant_id=request.tenant_id,
        persona_context={
            "persona": request.user_context.persona,
            "allowed_personas_by_agent": {
                candidate["agent_id"]: [request.user_context.persona] for candidate in enabled_agents
            },
            "historical_intent_hits": {},
        },
        candidates=enabled_agents,
    )

    logger.info(
        "execute.resolver_result",
        extra={
            "tenant_id": request.tenant_id,
            "persona": request.user_context.persona,
            "decision": resolution.decision,
            "selected_agent_id": resolution.selected_agent_id,
            "candidate_count": len(resolution.candidates),
            "top_candidates": [
                {
                    "agent_id": candidate.agent_id,
                    "final_score": candidate.final_score,
                    "semantic_score": candidate.semantic_score,
                    "rule_score": candidate.rule_score,
                    "context_score": candidate.context_score,
                }
                for candidate in resolution.candidates[:3]
            ],
        },
    )

    if resolution.decision == "fallback":
        logger.info(
            "execute.branch_fallback",
            extra={
                "tenant_id": request.tenant_id,
                "persona": request.user_context.persona,
                "reason": "resolver_decision_fallback",
                "clarification_question": resolution.clarification_question,
            },
        )
        return ExecutionResult(
            execution_id="",
            status="failed",
            state="FAILED",
            output_summary=resolution.clarification_question or "No safe agent match",
        )

    if resolution.decision == "clarification":
        logger.info(
            "execute.branch_clarification",
            extra={
                "tenant_id": request.tenant_id,
                "persona": request.user_context.persona,
                "clarification_question": resolution.clarification_question,
            },
        )
        return ExecutionResult(
            execution_id="",
            status="pending_confirmation",
            state="WAITING_CONFIRMATION",
            output_summary=resolution.clarification_question,
            requires_confirmation=True,
            next_actions=["clarify_intent"],
        )

    selected_agent_id = resolution.selected_agent_id
    if selected_agent_id is None:
        raise HTTPException(status_code=500, detail="Resolver returned no selected agent")

    try:
        agent_config = registry.load_agent(selected_agent_id, request.tenant_id)
    except (KeyError, PermissionError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    if agent_config.get("handler_class"):
        logger.info(
            "execute.handler_path_selected",
            extra={
                "tenant_id": request.tenant_id,
                "persona": request.user_context.persona,
                "selected_agent_id": selected_agent_id,
                "handler_class": agent_config.get("handler_class"),
            },
        )
        agent_result = await agent_executor.execute_action(
            tenant_id=request.tenant_id,
            template_id=selected_agent_id,
            user_id=request.user_context.user_id,
            user_persona=request.user_context.persona,
            trigger_payload={
                "query": request.query,
                "intent": selected_agent_id,
                "triggered_by": "api_execute",
                "confirmed": False,
            },
            claim_set={
                "query": request.query,
                "persona": request.user_context.persona,
                "department": request.user_context.department,
                "user_alias": request.user_context.user_id,
            },
            confirmed=False,
        )

        output_summary = (
            str(agent_result.output.get("message"))
            if agent_result.output.get("message")
            else (agent_result.error or "Execution finished")
        )
        state = {
            "success": "COMPLETED",
            "pending_confirmation": "WAITING_CONFIRMATION",
            "failed": "FAILED",
        }.get(agent_result.status, "FAILED")

        logger.info(
            "execute.handler_result",
            extra={
                "tenant_id": request.tenant_id,
                "selected_agent_id": selected_agent_id,
                "status": agent_result.status,
                "state": state,
                "requires_confirmation": agent_result.requires_confirmation,
                "output_summary": output_summary,
                "error": agent_result.error,
            },
        )

        return ExecutionResult(
            execution_id=agent_result.output.get("action_id", ""),
            status="completed" if agent_result.status == "success" else agent_result.status,
            state=state,
            output_summary=output_summary,
            requires_confirmation=agent_result.requires_confirmation,
            next_actions=["confirm", "cancel"] if agent_result.requires_confirmation else [],
        )

    orchestrator_result = orchestrator.execute(
        agent_config=agent_config,
        tenant_id=request.tenant_id,
        user_context=request.user_context.model_dump(),
        input_payload={"query": request.query, "confirmed": False},
    )
    logger.info(
        "execute.orchestrator_result",
        extra={
            "tenant_id": request.tenant_id,
            "selected_agent_id": selected_agent_id,
            "status": orchestrator_result.status,
            "state": orchestrator_result.state,
            "output_summary": orchestrator_result.output_summary,
        },
    )
    return orchestrator_result


@router.post("/confirm/{execution_id}", summary="Confirm a pending action")
def confirm(execution_id: str, request: ConfirmRequest) -> dict[str, str]:
    return {
        "execution_id": execution_id,
        "status": "resume_queued",
        "decision": request.decision,
        "actor_user_id": request.actor_user_id,
    }


@router.delete("/confirm/{execution_id}", summary="Cancel a pending action")
def cancel(execution_id: str) -> dict[str, str]:
    return {"execution_id": execution_id, "status": "cancelled"}


@router.get("/executions/{execution_id}/status", summary="Execution status")
def execution_status(execution_id: str) -> dict[str, str]:
    return {"execution_id": execution_id, "status": "unknown"}
