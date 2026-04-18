import logging

from fastapi import APIRouter, Depends, HTTPException

from app.agents.executor import AgentExecutor
from app.api.dependencies import get_agent_executor, get_orchestrator, get_registry_service
from app.schemas.actions import (
    ActionApprovalRequest,
    ActionExecuteRequest,
    ActionExecutionResponse,
    ActionRejectionRequest,
)
from app.schemas.execution import AdminExecuteByAgentRequest
from app.schemas.registry import TenantAgentConfigPatch, VersionPointerRequest
from app.services.orchestrator import ExecutionOrchestrator
from app.services.registry_service import (
    RegistryConflictError,
    RegistryService,
    RegistryValidationError,
)

router = APIRouter(prefix="/admin", tags=["tenant-admin"])
logger = logging.getLogger(__name__)


@router.get("/agents", summary="List agents from global library")
def list_agents(registry: RegistryService = Depends(get_registry_service)) -> dict[str, list[dict]]:
    return {"items": registry.list_global_library()}


@router.get("/agents/{agent_id}/config", summary="Get tenant config for an agent")
def get_agent_config(
    agent_id: str,
    tenant_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.get_tenant_agent_config(tenant_id=tenant_id, agent_id=agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/agents/{agent_id}/enable", summary="Enable an agent for tenant")
def enable_agent(
    agent_id: str,
    tenant_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.set_agent_enabled(tenant_id=tenant_id, agent_id=agent_id, enabled=True)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/agents/{agent_id}/disable", summary="Disable an agent for tenant")
def disable_agent(
    agent_id: str,
    tenant_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.set_agent_enabled(tenant_id=tenant_id, agent_id=agent_id, enabled=False)
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/agents/{agent_id}/config", summary="Update tenant config")
def update_agent_config(
    agent_id: str,
    tenant_id: str,
    patch: TenantAgentConfigPatch,
    actor_user_id: str | None = None,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.create_tenant_config_draft(
            tenant_id=tenant_id,
            agent_id=agent_id,
            patch=patch,
            actor_user_id=actor_user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RegistryValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/versions", summary="List tenant version history")
def list_agent_versions(
    agent_id: str,
    tenant_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.list_tenant_versions(tenant_id=tenant_id, agent_id=agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/publish", summary="Publish selected draft versions")
def publish_agent_versions(
    agent_id: str,
    request: VersionPointerRequest,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.publish_tenant_versions(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            definition_version_id=request.definition_version_id,
            config_version_id=request.config_version_id,
            actor_user_id=request.actor_user_id,
            notes=request.notes,
            expected_edit_version=request.expected_edit_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RegistryValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/agents/{agent_id}/rollback", summary="Rollback to previous version pointers")
def rollback_agent_versions(
    agent_id: str,
    request: VersionPointerRequest,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.rollback_tenant_versions(
            tenant_id=request.tenant_id,
            agent_id=agent_id,
            definition_version_id=request.definition_version_id,
            config_version_id=request.config_version_id,
            actor_user_id=request.actor_user_id,
            notes=request.notes,
            expected_edit_version=request.expected_edit_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RegistryValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/agent-executions", summary="Audit log for tenant agent runs")
def list_agent_executions() -> dict[str, list[dict[str, str]]]:
    return {"items": []}


@router.get("/trigger-rules", summary="List trigger rules")
def list_trigger_rules() -> dict[str, list[dict[str, str]]]:
    return {"items": []}


@router.post("/trigger-rules", summary="Create trigger rule")
def create_trigger_rule() -> dict[str, str]:
    return {"status": "not_implemented"}


@router.put("/trigger-rules/{rule_id}", summary="Update trigger rule")
def update_trigger_rule(rule_id: str) -> dict[str, str]:
    return {"rule_id": rule_id, "status": "not_implemented"}


@router.delete("/trigger-rules/{rule_id}", summary="Delete trigger rule")
def delete_trigger_rule(rule_id: str) -> dict[str, str]:
    return {"rule_id": rule_id, "status": "not_implemented"}


@router.post("/agents/{agent_id}/test", summary="Test run an agent with mock data")
def test_agent(agent_id: str, tenant_id: str) -> dict[str, str]:
    return {
        "agent_id": agent_id,
        "tenant_id": tenant_id,
        "status": "dry_run_queued",
    }


@router.post("/actions/execute", summary="Execute registered action workflow", response_model=ActionExecutionResponse)
def execute_actions(
    request: ActionExecuteRequest,
    dry_run: bool = False,
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> ActionExecutionResponse:
    try:
        result = orchestrator.execute_action_workflow(
            action_names=request.action_names,
            triggered_by=request.persona,
            payload=request.payload,
            mode=request.mode,
            dry_run=dry_run,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionExecutionResponse(**result)


@router.post("/actions/{execution_id}/approve", summary="Approve an awaiting action execution")
def approve_action_execution(
    execution_id: str,
    request: ActionApprovalRequest,
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> dict:
    try:
        return orchestrator.approve_action_execution(
            execution_id=execution_id,
            actor_user_id=request.actor_user_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/actions/{execution_id}/reject", summary="Reject an awaiting action execution")
def reject_action_execution(
    execution_id: str,
    request: ActionRejectionRequest,
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> dict:
    try:
        response = orchestrator.reject_action_execution(
            execution_id=execution_id,
            actor_user_id=request.actor_user_id,
        )
        if request.reason:
            response["reason"] = request.reason
        return response
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/actions/{execution_id}/audit", summary="Get action audit trail")
def action_audit(
    execution_id: str,
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> dict:
    try:
        return orchestrator.get_action_audit(execution_id=execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/actions/{execution_id}/status", summary="Get action execution status")
def action_status(
    execution_id: str,
    orchestrator: ExecutionOrchestrator = Depends(get_orchestrator),
) -> dict:
    try:
        return orchestrator.get_action_status(execution_id=execution_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/execute/by-agent/{agent_id}", summary="Diagnostic execution by explicit agent")
async def execute_by_agent(
    agent_id: str,
    request: AdminExecuteByAgentRequest,
    registry: RegistryService = Depends(get_registry_service),
    agent_executor: AgentExecutor = Depends(get_agent_executor),
) -> dict:
    logger.info(
        "admin.execute_by_agent.request_received",
        extra={
            "tenant_id": request.tenant_id,
            "agent_id": agent_id,
            "persona": request.persona,
            "query": request.query,
            "user_id": request.user_id,
        },
    )

    try:
        agent_config = registry.load_agent(agent_id, request.tenant_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    registry_diag = registry.debug_agent_runtime_snapshot(
        tenant_id=request.tenant_id,
        persona_type=request.persona,
        agent_id=agent_id,
    )
    logger.info("admin.execute_by_agent.registry_diagnostic", extra=registry_diag)

    handler_class = agent_config.get("handler_class")
    if not handler_class:
        raise HTTPException(
            status_code=422,
            detail="Selected agent does not expose handler_class; direct executor bypass requires handler path",
        )

    executor_input = {
        "tenant_id": request.tenant_id,
        "template_id": agent_config.get("agent_key", agent_id),
        "user_id": request.user_id,
        "user_persona": request.persona,
        "trigger_payload": {
            "query": request.query,
            "intent": agent_id,
            "triggered_by": "admin_execute_by_agent",
            "confirmed": request.confirmed,
        },
        "claim_set": {
            "query": request.query,
            "persona": request.persona,
            "department": request.department,
            "user_alias": request.user_id,
        },
        "confirmed": request.confirmed,
    }
    logger.info("admin.execute_by_agent.executor_input", extra=executor_input)

    result = await agent_executor.execute_action(**executor_input)
    state = {
        "success": "COMPLETED",
        "pending_confirmation": "WAITING_CONFIRMATION",
        "failed": "FAILED",
    }.get(result.status, "FAILED")
    output_summary = (
        str(result.output.get("message"))
        if isinstance(result.output, dict) and result.output.get("message")
        else (result.error or "Execution finished")
    )
    step_results = result.output.get("steps") if isinstance(result.output, dict) else None
    if step_results is None:
        step_results = [result.output]

    logger.info(
        "admin.execute_by_agent.executor_result",
        extra={
            "tenant_id": request.tenant_id,
            "agent_id": agent_id,
            "status": result.status,
            "state": state,
            "requires_confirmation": result.requires_confirmation,
            "output_summary": output_summary,
            "error": result.error,
            "step_results": step_results,
            "final_output": result.output,
        },
    )

    return {
        "execution_id": result.output.get("action_id", "") if isinstance(result.output, dict) else "",
        "status": result.status,
        "state": state,
        "output_summary": output_summary,
        "requires_confirmation": result.requires_confirmation,
        "step_results": step_results,
        "final_output": result.output,
        "error": result.error,
    }
