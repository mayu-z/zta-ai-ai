from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_registry_service
from app.schemas.registry import TenantAgentConfigPatch, VersionPointerRequest
from app.services.registry_service import (
    RegistryConflictError,
    RegistryService,
    RegistryValidationError,
)

router = APIRouter(prefix="/admin", tags=["tenant-admin"])


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
