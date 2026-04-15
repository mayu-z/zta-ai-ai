from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_intent_resolver, get_orchestrator, get_registry_service
from app.schemas.execution import ConfirmRequest, ExecuteRequest, ExecutionResult
from app.services.intent_resolver import IntentResolver
from app.services.orchestrator import ExecutionOrchestrator
from app.services.registry_service import RegistryService

router = APIRouter(tags=["execution"])


@router.post("/execute", summary="Execute agent from user query")
def execute(
    request: ExecuteRequest,
    registry: RegistryService = Depends(get_registry_service),
    resolver: IntentResolver = Depends(get_intent_resolver),
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> ExecutionResult:
    try:
        enabled_agents = registry.list_enabled_agents(
            tenant_id=request.tenant_id,
            persona_type=request.user_context.persona,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if not enabled_agents:
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

    if resolution.decision == "fallback":
        return ExecutionResult(
            execution_id="",
            status="failed",
            state="FAILED",
            output_summary=resolution.clarification_question or "No safe agent match",
        )

    if resolution.decision == "clarification":
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

    return orchestrator.execute(
        agent_config=agent_config,
        tenant_id=request.tenant_id,
        user_context=request.user_context.model_dump(),
        input_payload={"query": request.query, "confirmed": False},
    )


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
