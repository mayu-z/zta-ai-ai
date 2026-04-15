from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_registry_service
from app.schemas.registry import AgentDefinitionDraftRequest, AgentStatusPatch
from app.services.registry_service import (
    RegistryConflictError,
    RegistryService,
    RegistryValidationError,
)

router = APIRouter(prefix="/system", tags=["system-admin"])


@router.get("/agents", summary="List full global agent library")
def list_system_agents(registry: RegistryService = Depends(get_registry_service)) -> dict[str, list[dict]]:
    return {"items": registry.list_global_library()}


@router.post("/agents", summary="Create agent definition")
def create_system_agent(
    request: AgentDefinitionDraftRequest,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.create_definition_draft(
            definition_payload=request.definition.model_dump(),
            actor_user_id=request.actor_user_id,
        )
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RegistryValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/agents/{agent_id}", summary="Update agent definition")
def update_system_agent(
    agent_id: str,
    request: AgentDefinitionDraftRequest,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.update_definition_draft(
            agent_id=agent_id,
            definition_payload=request.definition.model_dump(),
            actor_user_id=request.actor_user_id,
            expected_base_version=request.expected_base_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RegistryConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (RegistryValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/agents/{agent_id}/status", summary="Update agent status")
def update_agent_status(
    agent_id: str,
    patch: AgentStatusPatch,
    registry: RegistryService = Depends(get_registry_service),
) -> dict[str, str]:
    try:
        return registry.update_agent_status(agent_id=agent_id, status=patch.status)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/versions", summary="List definition version history")
def list_definition_versions(
    agent_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict:
    try:
        return registry.list_definition_versions(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/agents/{agent_id}/tenants", summary="List tenants with this agent enabled")
def list_agent_tenants(
    agent_id: str,
    registry: RegistryService = Depends(get_registry_service),
) -> dict[str, list[dict]]:
    try:
        items = registry.list_agent_tenants(agent_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"agent_id": agent_id, "items": items}


@router.get("/executions", summary="Cross-tenant execution stats")
def system_execution_stats(
    registry: RegistryService = Depends(get_registry_service),
) -> dict[str, dict[str, int]]:
    return {"stats": registry.execution_stats()}
