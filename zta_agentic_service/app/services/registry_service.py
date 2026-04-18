import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.enums import AgentDefinitionStatus, PublishAction, PublishStatus, TriggerType
from app.db.models import (
    AgentDefinition,
    AgentDefinitionVersion,
    AgentExecution,
    RegistryPublishEvent,
    TenantAgentConfig,
    TenantAgentConfigVersion,
)
from app.schemas.registry import AgentDefinitionContract, TenantAgentConfigPatch
from app.services.cache import RegistryCache

logger = logging.getLogger(__name__)


class RegistryValidationError(ValueError):
    pass


class RegistryConflictError(RuntimeError):
    pass


class RegistryService:
    def __init__(self, db: Session, cache: RegistryCache | None = None):
        self.db = db
        self.cache = cache

    def load_agent(self, agent_id: str, tenant_id: str) -> dict[str, Any]:
        tenant_uuid = self._to_uuid(tenant_id)
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        tenant_cfg = self.db.scalar(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_uuid,
                TenantAgentConfig.agent_definition_id == definition.id,
            )
        )
        if tenant_cfg is None:
            raise PermissionError("Agent is not enabled for tenant")

        runtime_cfg = self._runtime_tenant_config(tenant_cfg)
        if not runtime_cfg["is_enabled"]:
            raise PermissionError("Agent is not enabled for tenant")

        runtime_definition = self._runtime_definition(
            definition=definition,
            active_definition_version_id=tenant_cfg.active_definition_version_id,
        )

        merged = {
            "agent_definition_id": str(definition.id),
            "template_id": runtime_definition["agent_key"],
            "agent_key": runtime_definition["agent_key"],
            "name": runtime_definition["name"],
            "description": runtime_definition["description"],
            "version": runtime_definition["version"],
            "domain": runtime_definition["domain"],
            "trigger_type": runtime_definition["trigger_type"],
            "trigger_config": runtime_definition["trigger_config"],
            "trigger_config_schema": runtime_definition["trigger_config_schema"],
            "required_data_scope": runtime_definition["required_data_scope"],
            "input_schema": runtime_definition["input_schema"],
            "output_schema": runtime_definition["output_schema"],
            "action_steps": runtime_definition["action_steps"],
            "rbac_permissions": runtime_definition["rbac_permissions"],
            "constraints": self._merge_constraints(
                runtime_definition["constraints"], runtime_cfg["custom_constraints"]
            ),
            "output_type": runtime_definition["output_type"],
            "requires_confirmation": runtime_definition["requires_confirmation"],
            "approval_level": runtime_definition["approval_level"],
            "allowed_personas": runtime_definition["allowed_personas"],
            "confirmation_prompt": runtime_definition["confirmation_prompt"],
            "chain_to": runtime_definition["chain_to"],
            "allowed_output_channels": runtime_definition["allowed_output_channels"],
            "handler_class": runtime_definition["handler_class"],
            "is_side_effect": runtime_definition["is_side_effect"],
            "risk_level": runtime_definition["risk_level"],
            "is_sensitive_monitor": runtime_definition["is_sensitive_monitor"],
            "is_active": runtime_definition["is_active"],
            "status": runtime_definition["status"],
            "risk_rank": runtime_definition["risk_rank"],
            "tenant_config_id": str(tenant_cfg.id),
            "instance_id": str(tenant_cfg.id),
            "tenant_id": str(tenant_cfg.tenant_id),
            "custom_templates": runtime_cfg["custom_templates"],
            "approval_config": runtime_cfg["approval_config"],
            "notification_channels": runtime_cfg["notification_channels"],
            "config": runtime_cfg["config"],
            "created_by": tenant_cfg.created_by,
            "last_triggered_at": tenant_cfg.last_triggered_at,
            "trigger_count": tenant_cfg.trigger_count,
            "definition_version_id": (
                str(tenant_cfg.active_definition_version_id)
                if tenant_cfg.active_definition_version_id
                else None
            ),
            "config_version_id": (
                str(tenant_cfg.active_config_version_id) if tenant_cfg.active_config_version_id else None
            ),
        }
        return merged

    def list_enabled_agents(self, tenant_id: str, persona_type: str) -> list[dict[str, Any]]:
        tenant_uuid = self._to_uuid(tenant_id)
        logger.info(
            "registry.list_enabled_agents.query_start",
            extra={
                "tenant_id": tenant_id,
                "tenant_uuid": str(tenant_uuid),
                "persona_type": persona_type,
                "where": {
                    "tenant_agent_configs.tenant_id": str(tenant_uuid),
                    "tenant_agent_configs.is_enabled": True,
                },
            },
        )
        stmt = (
            select(AgentDefinition, TenantAgentConfig)
            .join(TenantAgentConfig, TenantAgentConfig.agent_definition_id == AgentDefinition.id)
            .where(TenantAgentConfig.tenant_id == tenant_uuid, TenantAgentConfig.is_enabled.is_(True))
        )
        rows = self.db.execute(stmt).all()
        logger.info(
            "registry.list_enabled_agents.join_rows_loaded",
            extra={"tenant_id": tenant_id, "row_count": len(rows)},
        )

        enabled: list[dict[str, Any]] = []
        for definition, tenant_cfg in rows:
            runtime_definition = self._runtime_definition(
                definition=definition,
                active_definition_version_id=tenant_cfg.active_definition_version_id,
            )
            allowed = runtime_definition["allowed_personas"] or runtime_definition[
                "rbac_permissions"
            ].get("allowed_personas", [])
            if allowed and persona_type not in allowed:
                logger.info(
                    "registry.list_enabled_agents.persona_filtered_out",
                    extra={
                        "tenant_id": tenant_id,
                        "agent_id": runtime_definition["agent_key"],
                        "persona_type": persona_type,
                        "allowed_personas": allowed,
                    },
                )
                continue
            enabled.append(
                {
                    "agent_id": runtime_definition["agent_key"],
                    "name": runtime_definition["name"],
                    "description": runtime_definition["description"],
                    "keywords": runtime_definition["trigger_config"].get("keywords", []),
                    "risk_rank": runtime_definition["risk_rank"],
                    "handler_class": runtime_definition["handler_class"],
                    "output_type": runtime_definition["output_type"],
                    "requires_confirmation": runtime_definition["requires_confirmation"],
                    "tenant_config_id": str(tenant_cfg.id),
                }
            )
        logger.info(
            "registry.list_enabled_agents.query_done",
            extra={
                "tenant_id": tenant_id,
                "persona_type": persona_type,
                "enabled_count": len(enabled),
                "enabled_agent_ids": [item["agent_id"] for item in enabled],
            },
        )
        return enabled

    def debug_agent_runtime_snapshot(
        self,
        tenant_id: str,
        persona_type: str,
        agent_id: str,
    ) -> dict[str, Any]:
        tenant_uuid = self._to_uuid(tenant_id)
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            payload = {
                "tenant_id": tenant_id,
                "persona_type": persona_type,
                "agent_id": agent_id,
                "error": "agent_definition_not_found",
            }
            logger.info("registry.debug_agent_runtime_snapshot", extra=payload)
            return payload

        tenant_cfg = self.db.scalar(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_uuid,
                TenantAgentConfig.agent_definition_id == definition.id,
            )
        )
        if tenant_cfg is None:
            payload = {
                "tenant_id": tenant_id,
                "persona_type": persona_type,
                "agent_id": agent_id,
                "agent_definition_id": str(definition.id),
                "error": "tenant_config_not_found",
            }
            logger.info("registry.debug_agent_runtime_snapshot", extra=payload)
            return payload

        runtime_cfg = self._runtime_tenant_config(tenant_cfg)
        runtime_definition = self._runtime_definition(
            definition=definition,
            active_definition_version_id=tenant_cfg.active_definition_version_id,
        )
        allowed_personas = runtime_definition.get("allowed_personas") or runtime_definition.get(
            "rbac_permissions", {}
        ).get("allowed_personas", [])
        persona_allowed = bool(not allowed_personas or persona_type in allowed_personas)

        active_def_version_status = None
        active_cfg_version_status = None
        if tenant_cfg.active_definition_version_id is not None:
            def_ver = self.db.get(AgentDefinitionVersion, tenant_cfg.active_definition_version_id)
            active_def_version_status = def_ver.status.value if def_ver is not None else None
        if tenant_cfg.active_config_version_id is not None:
            cfg_ver = self.db.get(TenantAgentConfigVersion, tenant_cfg.active_config_version_id)
            active_cfg_version_status = cfg_ver.status.value if cfg_ver is not None else None

        payload = {
            "tenant_id": tenant_id,
            "tenant_uuid": str(tenant_uuid),
            "persona_type": persona_type,
            "agent_id": agent_id,
            "agent_definition": {
                "id": str(definition.id),
                "agent_key": definition.agent_key,
                "name": definition.name,
                "version": definition.version,
                "domain": definition.domain,
                "is_active": definition.is_active,
                "status": definition.status.value,
                "allowed_personas": definition.allowed_personas,
                "rbac_permissions": definition.rbac_permissions,
                "trigger_config": definition.trigger_config,
                "handler_class": definition.handler_class,
            },
            "tenant_config": {
                "id": str(tenant_cfg.id),
                "tenant_id": str(tenant_cfg.tenant_id),
                "agent_definition_id": str(tenant_cfg.agent_definition_id),
                "is_enabled": tenant_cfg.is_enabled,
                "active_definition_version_id": (
                    str(tenant_cfg.active_definition_version_id)
                    if tenant_cfg.active_definition_version_id
                    else None
                ),
                "active_config_version_id": (
                    str(tenant_cfg.active_config_version_id) if tenant_cfg.active_config_version_id else None
                ),
                "active_definition_version_status": active_def_version_status,
                "active_config_version_status": active_cfg_version_status,
                "edit_version": tenant_cfg.edit_version,
            },
            "runtime_expectations": {
                "where": {
                    "tenant_agent_configs.tenant_id": str(tenant_uuid),
                    "tenant_agent_configs.agent_definition_id": str(definition.id),
                    "tenant_agent_configs.is_enabled": True,
                },
                "persona_allowed": persona_allowed,
                "allowed_personas": allowed_personas,
                "runtime_is_enabled": runtime_cfg.get("is_enabled"),
                "runtime_is_active": runtime_definition.get("is_active"),
                "runtime_status": runtime_definition.get("status"),
            },
        }
        logger.info("registry.debug_agent_runtime_snapshot", extra=payload)
        return payload

    def list_global_library(self) -> list[dict[str, Any]]:
        rows = self.db.scalars(select(AgentDefinition)).all()
        return [
            {
                "agent_id": row.agent_key,
                "name": row.name,
                "description": row.description,
                "version": row.version,
                "handler_class": row.handler_class,
                "is_active": row.is_active,
                "status": row.status.value,
            }
            for row in rows
        ]

    def get_tenant_agent_config(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        tenant_uuid = self._to_uuid(tenant_id)
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        cfg = self.db.scalar(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_uuid,
                TenantAgentConfig.agent_definition_id == definition.id,
            )
        )
        if cfg is None:
            raise KeyError("Tenant config not found")

        return {
            "id": str(cfg.id),
            "instance_id": str(cfg.id),
            "tenant_id": str(cfg.tenant_id),
            "agent_definition_id": str(cfg.agent_definition_id),
            "is_enabled": cfg.is_enabled,
            "custom_templates": cfg.custom_templates,
            "custom_constraints": cfg.custom_constraints,
            "approval_config": cfg.approval_config,
            "notification_channels": cfg.notification_channels,
            "config": cfg.config,
            "created_by": cfg.created_by,
            "last_triggered_at": cfg.last_triggered_at,
            "trigger_count": cfg.trigger_count,
            "edit_version": cfg.edit_version,
        }

    def set_agent_enabled(self, tenant_id: str, agent_id: str, enabled: bool) -> dict[str, Any]:
        tenant_uuid = self._to_uuid(tenant_id)
        try:
            definition = self._get_definition_for_agent_id(agent_id)
            if definition is None:
                raise KeyError(f"Unknown agent: {agent_id}")

            cfg = self.db.scalar(
                select(TenantAgentConfig).where(
                    TenantAgentConfig.tenant_id == tenant_uuid,
                    TenantAgentConfig.agent_definition_id == definition.id,
                )
            )
            if cfg is None:
                cfg = TenantAgentConfig(
                    tenant_id=tenant_uuid,
                    agent_definition_id=definition.id,
                    is_enabled=enabled,
                )
                self.db.add(cfg)
            else:
                cfg.is_enabled = enabled
                cfg.edit_version += 1

            self.db.commit()
            self._invalidate_tenant_cache(str(cfg.tenant_id))
            return {
                "tenant_id": str(cfg.tenant_id),
                "agent_id": definition.agent_key,
                "instance_id": str(cfg.id),
                "is_enabled": cfg.is_enabled,
            }
        except Exception:
            self.db.rollback()
            raise

    def list_agent_tenants(self, agent_id: str) -> list[dict[str, Any]]:
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        rows = self.db.scalars(
            select(TenantAgentConfig).where(TenantAgentConfig.agent_definition_id == definition.id)
        ).all()
        return [
            {
                "tenant_id": str(row.tenant_id),
                "instance_id": str(row.id),
                "is_enabled": row.is_enabled,
                "edit_version": row.edit_version,
            }
            for row in rows
        ]

    def execution_stats(self) -> dict[str, int]:
        rows = self.db.scalars(select(AgentExecution)).all()
        stats: dict[str, int] = {}
        for row in rows:
            key = row.status.value
            stats[key] = stats.get(key, 0) + 1
        return stats

    def validate_agent_config(self, agent_definition: dict[str, Any]) -> AgentDefinitionContract:
        try:
            return AgentDefinitionContract.model_validate(agent_definition)
        except Exception as exc:
            raise RegistryValidationError(str(exc)) from exc

    def create_definition_draft(
        self,
        definition_payload: dict[str, Any],
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        return self._save_definition_draft(
            definition_payload=definition_payload,
            actor_user_id=actor_user_id,
            require_existing=False,
        )

    def update_definition_draft(
        self,
        agent_id: str,
        definition_payload: dict[str, Any],
        actor_user_id: str | None = None,
        expected_base_version: str | None = None,
    ) -> dict[str, Any]:
        if definition_payload.get("agent_key") != agent_id:
            raise RegistryValidationError("Path agent_id and payload definition.agent_key must match")
        return self._save_definition_draft(
            definition_payload=definition_payload,
            actor_user_id=actor_user_id,
            require_existing=True,
            expected_base_version=expected_base_version,
        )

    def create_tenant_config_draft(
        self,
        tenant_id: str,
        agent_id: str,
        patch: TenantAgentConfigPatch,
        actor_user_id: str | None = None,
    ) -> dict[str, Any]:
        patch_fields = patch.model_dump(exclude_none=True)
        expected_edit_version = patch_fields.pop("edit_version", None)
        actor_uuid = self._to_uuid_or_none(actor_user_id)

        try:
            definition, tenant_cfg = self._get_or_create_tenant_config(tenant_id=tenant_id, agent_id=agent_id)

            if expected_edit_version is not None and tenant_cfg.edit_version != expected_edit_version:
                raise RegistryConflictError(
                    f"edit_version mismatch: expected {expected_edit_version}, found {tenant_cfg.edit_version}"
                )

            snapshot = self._runtime_tenant_config(tenant_cfg)
            snapshot.update(patch_fields)
            config_version = self._create_config_version_row(
                tenant_agent_config_id=tenant_cfg.id,
                snapshot=snapshot,
                created_by=actor_uuid,
            )
            if actor_user_id:
                tenant_cfg.created_by = actor_user_id
            tenant_cfg.edit_version += 1

            self.db.commit()
            return {
                "tenant_id": tenant_id,
                "agent_id": definition.agent_key,
                "tenant_config_id": str(tenant_cfg.id),
                "draft_config_version_id": str(config_version.id),
                "draft_config_version_number": config_version.version_number,
                "status": config_version.status.value,
                "edit_version": tenant_cfg.edit_version,
            }
        except Exception:
            self.db.rollback()
            raise

    def list_definition_versions(self, agent_id: str) -> dict[str, Any]:
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        rows = self.db.scalars(
            select(AgentDefinitionVersion)
            .where(AgentDefinitionVersion.agent_definition_id == definition.id)
            .order_by(AgentDefinitionVersion.version_number.desc())
        ).all()

        return {
            "agent_id": definition.agent_key,
            "items": [
                {
                    "version_id": str(row.id),
                    "version_number": row.version_number,
                    "status": row.status.value,
                    "schema_hash": row.schema_hash,
                    "created_at": row.created_at,
                    "published_at": row.published_at,
                }
                for row in rows
            ],
        }

    def list_tenant_versions(self, tenant_id: str, agent_id: str) -> dict[str, Any]:
        definition, tenant_cfg = self._get_tenant_config(tenant_id=tenant_id, agent_id=agent_id)

        definition_versions = self.db.scalars(
            select(AgentDefinitionVersion)
            .where(AgentDefinitionVersion.agent_definition_id == definition.id)
            .order_by(AgentDefinitionVersion.version_number.desc())
        ).all()
        config_versions = self.db.scalars(
            select(TenantAgentConfigVersion)
            .where(TenantAgentConfigVersion.tenant_agent_config_id == tenant_cfg.id)
            .order_by(TenantAgentConfigVersion.version_number.desc())
        ).all()

        return {
            "tenant_id": tenant_id,
            "agent_id": definition.agent_key,
            "tenant_config_id": str(tenant_cfg.id),
            "active_definition_version_id": (
                str(tenant_cfg.active_definition_version_id)
                if tenant_cfg.active_definition_version_id
                else None
            ),
            "active_config_version_id": (
                str(tenant_cfg.active_config_version_id) if tenant_cfg.active_config_version_id else None
            ),
            "edit_version": tenant_cfg.edit_version,
            "definition_versions": [
                {
                    "version_id": str(row.id),
                    "version_number": row.version_number,
                    "status": row.status.value,
                    "created_at": row.created_at,
                    "published_at": row.published_at,
                }
                for row in definition_versions
            ],
            "config_versions": [
                {
                    "version_id": str(row.id),
                    "version_number": row.version_number,
                    "status": row.status.value,
                    "created_at": row.created_at,
                    "published_at": row.published_at,
                }
                for row in config_versions
            ],
        }

    def publish_tenant_versions(
        self,
        tenant_id: str,
        agent_id: str,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None = None,
        expected_edit_version: int | None = None,
    ) -> dict[str, Any]:
        definition, tenant_cfg = self._get_tenant_config(tenant_id=tenant_id, agent_id=agent_id)
        return self._publish_with_tenant_config(
            tenant_cfg=tenant_cfg,
            definition=definition,
            definition_version_id=definition_version_id,
            config_version_id=config_version_id,
            actor_user_id=actor_user_id,
            notes=notes,
            expected_edit_version=expected_edit_version,
        )

    def rollback_tenant_versions(
        self,
        tenant_id: str,
        agent_id: str,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None = None,
        expected_edit_version: int | None = None,
    ) -> dict[str, Any]:
        definition, tenant_cfg = self._get_tenant_config(tenant_id=tenant_id, agent_id=agent_id)
        return self._rollback_with_tenant_config(
            tenant_cfg=tenant_cfg,
            definition=definition,
            definition_version_id=definition_version_id,
            config_version_id=config_version_id,
            actor_user_id=actor_user_id,
            notes=notes,
            expected_edit_version=expected_edit_version,
        )

    def update_agent_status(self, agent_id: str, status: str) -> dict[str, str]:
        try:
            definition = self._get_definition_for_agent_id(agent_id)
            if definition is None:
                raise KeyError(f"Unknown agent: {agent_id}")
            definition.status = AgentDefinitionStatus(status)
            self.db.commit()
            return {"agent_id": definition.agent_key, "status": definition.status.value}
        except Exception:
            self.db.rollback()
            raise

    def create_definition_version(
        self,
        agent_definition_id: str,
        snapshot: dict[str, Any],
        created_by: str | None = None,
    ) -> AgentDefinitionVersion:
        try:
            row = self._create_definition_version_row(
                agent_definition_id=self._to_uuid(agent_definition_id),
                snapshot=snapshot,
                created_by=self._to_uuid_or_none(created_by),
            )
            self.db.commit()
            return row
        except Exception:
            self.db.rollback()
            raise

    def publish_definition_version(
        self,
        tenant_config_id: str,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None = None,
    ) -> None:
        tenant_cfg = self.db.get(TenantAgentConfig, self._to_uuid(tenant_config_id))
        if tenant_cfg is None:
            raise KeyError("Unknown tenant config")
        definition = self.db.get(AgentDefinition, tenant_cfg.agent_definition_id)
        if definition is None:
            raise KeyError("Unknown agent definition")

        self._publish_with_tenant_config(
            tenant_cfg=tenant_cfg,
            definition=definition,
            definition_version_id=definition_version_id,
            config_version_id=config_version_id,
            actor_user_id=actor_user_id,
            notes=notes,
            expected_edit_version=None,
        )

    def rollback_definition_version(
        self,
        tenant_config_id: str,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None = None,
    ) -> None:
        tenant_cfg = self.db.get(TenantAgentConfig, self._to_uuid(tenant_config_id))
        if tenant_cfg is None:
            raise KeyError("Unknown tenant config")
        definition = self.db.get(AgentDefinition, tenant_cfg.agent_definition_id)
        if definition is None:
            raise KeyError("Unknown agent definition")

        self._rollback_with_tenant_config(
            tenant_cfg=tenant_cfg,
            definition=definition,
            definition_version_id=definition_version_id,
            config_version_id=config_version_id,
            actor_user_id=actor_user_id,
            notes=notes,
            expected_edit_version=None,
        )

    def _save_definition_draft(
        self,
        definition_payload: dict[str, Any],
        actor_user_id: str | None,
        require_existing: bool,
        expected_base_version: str | None = None,
    ) -> dict[str, Any]:
        contract = self.validate_agent_config(definition_payload)
        snapshot = contract.model_dump()
        actor_uuid = self._to_uuid_or_none(actor_user_id)

        try:
            definition = self.db.scalar(
                select(AgentDefinition).where(AgentDefinition.agent_key == contract.agent_key)
            )

            if definition is None and require_existing:
                raise KeyError(f"Unknown agent: {contract.agent_key}")
            if definition is not None and not require_existing:
                raise RegistryConflictError(f"Agent already exists: {contract.agent_key}")

            if definition is not None and expected_base_version and definition.version != expected_base_version:
                raise RegistryConflictError(
                    f"base version mismatch: expected {expected_base_version}, found {definition.version}"
                )

            if definition is None:
                definition = AgentDefinition(
                    agent_key=contract.agent_key,
                    name=contract.name,
                    description=contract.description,
                    version=contract.version,
                    domain=contract.domain,
                    trigger_type=TriggerType(contract.trigger_type),
                    trigger_config=contract.trigger_config,
                    trigger_config_schema=contract.trigger_config_schema,
                    required_data_scope=contract.required_data_scope,
                    input_schema=contract.input_schema,
                    output_schema=contract.output_schema,
                    action_steps=[step.model_dump() for step in contract.action_steps],
                    rbac_permissions=self._normalize_rbac(
                        contract.rbac_permissions, contract.allowed_personas
                    ),
                    constraints=contract.constraints,
                    output_type=contract.output_type,
                    requires_confirmation=contract.requires_confirmation,
                    approval_level=contract.approval_level,
                    allowed_personas=contract.allowed_personas,
                    confirmation_prompt=contract.confirmation_prompt,
                    chain_to=contract.chain_to,
                    allowed_output_channels=contract.allowed_output_channels,
                    handler_class=contract.handler_class,
                    is_side_effect=contract.is_side_effect,
                    risk_level=contract.risk_level,
                    is_sensitive_monitor=contract.is_sensitive_monitor,
                    is_active=contract.is_active,
                    status=AgentDefinitionStatus(contract.status),
                    risk_rank=contract.risk_rank,
                )
                self.db.add(definition)
                self.db.flush()
            else:
                definition.name = contract.name
                definition.description = contract.description
                definition.version = contract.version
                definition.domain = contract.domain
                definition.trigger_type = TriggerType(contract.trigger_type)
                definition.trigger_config = contract.trigger_config
                definition.trigger_config_schema = contract.trigger_config_schema
                definition.required_data_scope = contract.required_data_scope
                definition.input_schema = contract.input_schema
                definition.output_schema = contract.output_schema
                definition.action_steps = [step.model_dump() for step in contract.action_steps]
                definition.rbac_permissions = self._normalize_rbac(
                    contract.rbac_permissions, contract.allowed_personas
                )
                definition.constraints = contract.constraints
                definition.output_type = contract.output_type
                definition.requires_confirmation = contract.requires_confirmation
                definition.approval_level = contract.approval_level
                definition.allowed_personas = contract.allowed_personas
                definition.confirmation_prompt = contract.confirmation_prompt
                definition.chain_to = contract.chain_to
                definition.allowed_output_channels = contract.allowed_output_channels
                definition.handler_class = contract.handler_class
                definition.is_side_effect = contract.is_side_effect
                definition.risk_level = contract.risk_level
                definition.is_sensitive_monitor = contract.is_sensitive_monitor
                definition.is_active = contract.is_active
                definition.status = AgentDefinitionStatus(contract.status)
                definition.risk_rank = contract.risk_rank

            version_row = self._create_definition_version_row(
                agent_definition_id=definition.id,
                snapshot=snapshot,
                created_by=actor_uuid,
            )

            self.db.commit()
            return {
                "agent_id": definition.agent_key,
                "agent_definition_id": str(definition.id),
                "draft_definition_version_id": str(version_row.id),
                "draft_definition_version_number": version_row.version_number,
                "status": version_row.status.value,
            }
        except Exception:
            self.db.rollback()
            raise

    def _publish_with_tenant_config(
        self,
        tenant_cfg: TenantAgentConfig,
        definition: AgentDefinition,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None,
        expected_edit_version: int | None,
    ) -> dict[str, Any]:
        def_ver_id = self._to_uuid(definition_version_id)
        cfg_ver_id = self._to_uuid(config_version_id)

        try:
            if expected_edit_version is not None and tenant_cfg.edit_version != expected_edit_version:
                raise RegistryConflictError(
                    f"edit_version mismatch: expected {expected_edit_version}, found {tenant_cfg.edit_version}"
                )

            def_ver = self.db.get(AgentDefinitionVersion, def_ver_id)
            cfg_ver = self.db.get(TenantAgentConfigVersion, cfg_ver_id)
            if def_ver is None or cfg_ver is None:
                raise KeyError("Version does not exist")
            if def_ver.agent_definition_id != definition.id:
                raise RegistryValidationError("Definition version does not belong to requested agent")
            if cfg_ver.tenant_agent_config_id != tenant_cfg.id:
                raise RegistryValidationError("Config version does not belong to requested tenant config")

            def_ver.status = PublishStatus.PUBLISHED
            def_ver.published_at = datetime.now(UTC)
            cfg_ver.status = PublishStatus.PUBLISHED
            cfg_ver.published_at = datetime.now(UTC)

            # Keep hot-path config columns aligned with the currently active version.
            self._apply_config_snapshot(tenant_cfg, cfg_ver.snapshot)
            tenant_cfg.active_definition_version_id = def_ver.id
            tenant_cfg.active_config_version_id = cfg_ver.id
            tenant_cfg.edit_version += 1

            self.db.add(
                RegistryPublishEvent(
                    tenant_id=tenant_cfg.tenant_id,
                    agent_definition_id=tenant_cfg.agent_definition_id,
                    definition_version_id=def_ver.id,
                    config_version_id=cfg_ver.id,
                    action=PublishAction.PUBLISH,
                    actor_user_id=self._to_uuid_or_none(actor_user_id),
                    notes=notes,
                    event_metadata={"mode": "atomic_pointer_swap"},
                )
            )
            self.db.commit()
            self._invalidate_tenant_cache(str(tenant_cfg.tenant_id))
            return {
                "tenant_id": str(tenant_cfg.tenant_id),
                "agent_id": definition.agent_key,
                "active_definition_version_id": str(tenant_cfg.active_definition_version_id),
                "active_config_version_id": str(tenant_cfg.active_config_version_id),
                "edit_version": tenant_cfg.edit_version,
                "status": "published",
            }
        except Exception:
            self.db.rollback()
            raise

    def _rollback_with_tenant_config(
        self,
        tenant_cfg: TenantAgentConfig,
        definition: AgentDefinition,
        definition_version_id: str,
        config_version_id: str,
        actor_user_id: str | None,
        notes: str | None,
        expected_edit_version: int | None,
    ) -> dict[str, Any]:
        def_ver_id = self._to_uuid(definition_version_id)
        cfg_ver_id = self._to_uuid(config_version_id)

        try:
            if expected_edit_version is not None and tenant_cfg.edit_version != expected_edit_version:
                raise RegistryConflictError(
                    f"edit_version mismatch: expected {expected_edit_version}, found {tenant_cfg.edit_version}"
                )

            def_ver = self.db.get(AgentDefinitionVersion, def_ver_id)
            cfg_ver = self.db.get(TenantAgentConfigVersion, cfg_ver_id)
            if def_ver is None or cfg_ver is None:
                raise KeyError("Version does not exist")
            if def_ver.agent_definition_id != definition.id:
                raise RegistryValidationError("Definition version does not belong to requested agent")
            if cfg_ver.tenant_agent_config_id != tenant_cfg.id:
                raise RegistryValidationError("Config version does not belong to requested tenant config")

            self._apply_config_snapshot(tenant_cfg, cfg_ver.snapshot)
            tenant_cfg.active_definition_version_id = def_ver.id
            tenant_cfg.active_config_version_id = cfg_ver.id
            tenant_cfg.edit_version += 1

            self.db.add(
                RegistryPublishEvent(
                    tenant_id=tenant_cfg.tenant_id,
                    agent_definition_id=tenant_cfg.agent_definition_id,
                    definition_version_id=def_ver.id,
                    config_version_id=cfg_ver.id,
                    action=PublishAction.ROLLBACK,
                    actor_user_id=self._to_uuid_or_none(actor_user_id),
                    notes=notes,
                    event_metadata={"mode": "pointer_rewind"},
                )
            )
            self.db.commit()
            self._invalidate_tenant_cache(str(tenant_cfg.tenant_id))
            return {
                "tenant_id": str(tenant_cfg.tenant_id),
                "agent_id": definition.agent_key,
                "active_definition_version_id": str(tenant_cfg.active_definition_version_id),
                "active_config_version_id": str(tenant_cfg.active_config_version_id),
                "edit_version": tenant_cfg.edit_version,
                "status": "rolled_back",
            }
        except Exception:
            self.db.rollback()
            raise

    def _get_tenant_config(self, tenant_id: str, agent_id: str) -> tuple[AgentDefinition, TenantAgentConfig]:
        tenant_uuid = self._to_uuid(tenant_id)
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        tenant_cfg = self.db.scalar(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_uuid,
                TenantAgentConfig.agent_definition_id == definition.id,
            )
        )
        if tenant_cfg is None:
            raise KeyError("Tenant config not found")

        return definition, tenant_cfg

    def _get_or_create_tenant_config(
        self,
        tenant_id: str,
        agent_id: str,
    ) -> tuple[AgentDefinition, TenantAgentConfig]:
        tenant_uuid = self._to_uuid(tenant_id)
        definition = self._get_definition_for_agent_id(agent_id)
        if definition is None:
            raise KeyError(f"Unknown agent: {agent_id}")

        tenant_cfg = self.db.scalar(
            select(TenantAgentConfig).where(
                TenantAgentConfig.tenant_id == tenant_uuid,
                TenantAgentConfig.agent_definition_id == definition.id,
            )
        )
        if tenant_cfg is None:
            tenant_cfg = TenantAgentConfig(
                tenant_id=tenant_uuid,
                agent_definition_id=definition.id,
                is_enabled=False,
                edit_version=0,
            )
            self.db.add(tenant_cfg)
            self.db.flush()

        return definition, tenant_cfg

    def _runtime_definition(
        self,
        definition: AgentDefinition,
        active_definition_version_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        payload = {
            "agent_key": definition.agent_key,
            "name": definition.name,
            "description": definition.description,
            "version": definition.version,
            "domain": definition.domain,
            "trigger_type": definition.trigger_type.value,
            "trigger_config": definition.trigger_config,
            "trigger_config_schema": definition.trigger_config_schema,
            "required_data_scope": definition.required_data_scope,
            "input_schema": definition.input_schema,
            "output_schema": definition.output_schema,
            "action_steps": definition.action_steps,
            "rbac_permissions": definition.rbac_permissions,
            "constraints": definition.constraints,
            "output_type": definition.output_type,
            "requires_confirmation": definition.requires_confirmation,
            "approval_level": definition.approval_level,
            "allowed_personas": definition.allowed_personas,
            "confirmation_prompt": definition.confirmation_prompt,
            "chain_to": definition.chain_to,
            "allowed_output_channels": definition.allowed_output_channels,
            "handler_class": definition.handler_class,
            "is_side_effect": definition.is_side_effect,
            "risk_level": definition.risk_level,
            "is_sensitive_monitor": definition.is_sensitive_monitor,
            "is_active": definition.is_active,
            "status": definition.status.value,
            "risk_rank": definition.risk_rank,
        }

        if active_definition_version_id is None:
            return payload

        version_row = self.db.get(AgentDefinitionVersion, active_definition_version_id)
        if version_row is None or not isinstance(version_row.snapshot, dict):
            return payload

        snapshot = version_row.snapshot
        payload.update(
            {
                "agent_key": snapshot.get("agent_key", payload["agent_key"]),
                "name": snapshot.get("name", payload["name"]),
                "description": snapshot.get("description", payload["description"]),
                "version": snapshot.get("version", payload["version"]),
                "domain": snapshot.get("domain", payload["domain"]),
                "trigger_type": snapshot.get("trigger_type", payload["trigger_type"]),
                "trigger_config": snapshot.get("trigger_config", payload["trigger_config"]),
                "trigger_config_schema": snapshot.get(
                    "trigger_config_schema", payload["trigger_config_schema"]
                ),
                "required_data_scope": snapshot.get(
                    "required_data_scope", payload["required_data_scope"]
                ),
                "input_schema": snapshot.get("input_schema", payload["input_schema"]),
                "output_schema": snapshot.get("output_schema", payload["output_schema"]),
                "action_steps": snapshot.get("action_steps", payload["action_steps"]),
                "rbac_permissions": snapshot.get("rbac_permissions", payload["rbac_permissions"]),
                "constraints": snapshot.get("constraints", payload["constraints"]),
                "output_type": snapshot.get("output_type", payload["output_type"]),
                "requires_confirmation": snapshot.get(
                    "requires_confirmation", payload["requires_confirmation"]
                ),
                "approval_level": snapshot.get("approval_level", payload["approval_level"]),
                "allowed_personas": snapshot.get("allowed_personas", payload["allowed_personas"]),
                "confirmation_prompt": snapshot.get(
                    "confirmation_prompt", payload["confirmation_prompt"]
                ),
                "chain_to": snapshot.get("chain_to", payload["chain_to"]),
                "allowed_output_channels": snapshot.get(
                    "allowed_output_channels", payload["allowed_output_channels"]
                ),
                "handler_class": snapshot.get("handler_class", payload["handler_class"]),
                "is_side_effect": snapshot.get("is_side_effect", payload["is_side_effect"]),
                "risk_level": snapshot.get("risk_level", payload["risk_level"]),
                "is_sensitive_monitor": snapshot.get(
                    "is_sensitive_monitor", payload["is_sensitive_monitor"]
                ),
                "is_active": snapshot.get("is_active", payload["is_active"]),
                "status": snapshot.get("status", payload["status"]),
                "risk_rank": snapshot.get("risk_rank", payload["risk_rank"]),
            }
        )
        return payload

    def _runtime_tenant_config(self, tenant_cfg: TenantAgentConfig) -> dict[str, Any]:
        payload = {
            "is_enabled": tenant_cfg.is_enabled,
            "custom_templates": tenant_cfg.custom_templates,
            "custom_constraints": tenant_cfg.custom_constraints,
            "approval_config": tenant_cfg.approval_config,
            "notification_channels": tenant_cfg.notification_channels,
            "config": tenant_cfg.config,
        }

        if tenant_cfg.active_config_version_id is None:
            return payload

        version_row = self.db.get(TenantAgentConfigVersion, tenant_cfg.active_config_version_id)
        if version_row is None or not isinstance(version_row.snapshot, dict):
            return payload

        snapshot = version_row.snapshot
        payload.update(
            {
                "is_enabled": snapshot.get("is_enabled", payload["is_enabled"]),
                "custom_templates": snapshot.get("custom_templates", payload["custom_templates"]),
                "custom_constraints": snapshot.get(
                    "custom_constraints", payload["custom_constraints"]
                ),
                "approval_config": snapshot.get("approval_config", payload["approval_config"]),
                "notification_channels": snapshot.get(
                    "notification_channels", payload["notification_channels"]
                ),
                "config": snapshot.get("config", payload["config"]),
            }
        )
        return payload

    def _apply_config_snapshot(self, tenant_cfg: TenantAgentConfig, snapshot: dict[str, Any]) -> None:
        tenant_cfg.is_enabled = bool(snapshot.get("is_enabled", tenant_cfg.is_enabled))
        tenant_cfg.custom_templates = snapshot.get("custom_templates", tenant_cfg.custom_templates)
        tenant_cfg.custom_constraints = snapshot.get("custom_constraints", tenant_cfg.custom_constraints)
        tenant_cfg.approval_config = snapshot.get("approval_config", tenant_cfg.approval_config)
        tenant_cfg.notification_channels = snapshot.get(
            "notification_channels", tenant_cfg.notification_channels
        )
        tenant_cfg.config = snapshot.get("config", tenant_cfg.config)

    def _create_definition_version_row(
        self,
        agent_definition_id: uuid.UUID,
        snapshot: dict[str, Any],
        created_by: uuid.UUID | None,
    ) -> AgentDefinitionVersion:
        next_version = self._next_definition_version(agent_definition_id)
        schema_hash = self._snapshot_hash(snapshot)
        row = AgentDefinitionVersion(
            agent_definition_id=agent_definition_id,
            version_number=next_version,
            snapshot=snapshot,
            schema_hash=schema_hash,
            status=PublishStatus.DRAFT,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _create_config_version_row(
        self,
        tenant_agent_config_id: uuid.UUID,
        snapshot: dict[str, Any],
        created_by: uuid.UUID | None,
    ) -> TenantAgentConfigVersion:
        next_version = self._next_config_version(tenant_agent_config_id)
        schema_hash = self._snapshot_hash(snapshot)
        row = TenantAgentConfigVersion(
            tenant_agent_config_id=tenant_agent_config_id,
            version_number=next_version,
            snapshot=snapshot,
            schema_hash=schema_hash,
            status=PublishStatus.DRAFT,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _next_definition_version(self, agent_definition_id: uuid.UUID) -> int:
        stmt = select(AgentDefinitionVersion.version_number).where(
            AgentDefinitionVersion.agent_definition_id == agent_definition_id
        )
        current = [row[0] for row in self.db.execute(stmt).all()]
        return (max(current) if current else 0) + 1

    def _next_config_version(self, tenant_agent_config_id: uuid.UUID) -> int:
        stmt = select(TenantAgentConfigVersion.version_number).where(
            TenantAgentConfigVersion.tenant_agent_config_id == tenant_agent_config_id
        )
        current = [row[0] for row in self.db.execute(stmt).all()]
        return (max(current) if current else 0) + 1

    @staticmethod
    def _snapshot_hash(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    @staticmethod
    def _normalize_rbac(rbac: dict[str, Any], allowed_personas: list[str]) -> dict[str, Any]:
        merged = dict(rbac or {})
        if allowed_personas:
            merged["allowed_personas"] = allowed_personas
        return merged

    def _invalidate_tenant_cache(self, tenant_id: str) -> None:
        if self.cache is None:
            return
        try:
            self.cache.invalidate_tenant(tenant_id)
        except Exception:
            # Cache failures should not block registry state transitions.
            return

    @staticmethod
    def _to_uuid(value: str) -> uuid.UUID:
        return uuid.UUID(str(value))

    def _get_definition_for_agent_id(self, agent_id: str) -> AgentDefinition | None:
        candidates = self._agent_key_candidates(agent_id)
        for candidate in candidates:
            row = self.db.scalar(select(AgentDefinition).where(AgentDefinition.agent_key == candidate))
            if row is not None:
                return row

        lowered_candidates = [candidate.lower() for candidate in candidates]
        stmt = select(AgentDefinition).where(func.lower(AgentDefinition.agent_key).in_(lowered_candidates))
        return self.db.scalar(stmt)

    @staticmethod
    def _agent_key_candidates(agent_id: str) -> list[str]:
        raw = str(agent_id or "").strip()
        if not raw:
            return []

        normalized = raw.lower()
        if normalized.endswith("_agent"):
            normalized = f"{normalized[:-6]}_v1"

        candidates: list[str] = []
        for value in (raw, normalized):
            if value and value not in candidates:
                candidates.append(value)
        return candidates

    @staticmethod
    def _to_uuid_or_none(value: str | None) -> uuid.UUID | None:
        if value is None:
            return None
        return uuid.UUID(str(value))

    @staticmethod
    def _merge_constraints(base: dict[str, Any], tenant_override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base or {})
        for key, value in (tenant_override or {}).items():
            merged[key] = value
        return merged
