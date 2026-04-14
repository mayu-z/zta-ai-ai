from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agentic.db_models import AgenticActionConfigModel
from app.agentic.registry.agent_registry import AgentDefinitionLoader
from app.agentic.registry.schema_validator import (
    AgentDefinitionSchemaValidator,
    AgentDefinitionValidationError,
)
from app.core.exceptions import ValidationError
from app.core.redis_client import redis_client


class AgentDefinitionOverrideService:
    _OVERRIDE_KEY = "agent_definition_override"
    _UPDATED_BY_KEY = "agent_definition_override_updated_by"
    _UPDATED_AT_KEY = "agent_definition_override_updated_at"

    def __init__(
        self,
        loader: AgentDefinitionLoader | None = None,
        schema_validator: AgentDefinitionSchemaValidator | None = None,
    ) -> None:
        self._loader = loader or AgentDefinitionLoader()
        self._schema_validator = schema_validator or AgentDefinitionSchemaValidator()

    def list_definitions(self, *, db: Session, tenant_id: str) -> list[dict[str, Any]]:
        tenant_uuid = self._parse_tenant_uuid(tenant_id)
        definition_paths = sorted(self._loader._definitions_dir.glob("*.json"))
        if not definition_paths:
            return []

        agent_ids = [path.stem for path in definition_paths]
        rows = db.scalars(
            select(AgenticActionConfigModel)
            .where(AgenticActionConfigModel.tenant_id == str(tenant_uuid))
            .where(AgenticActionConfigModel.action_id.in_(agent_ids))
        ).all()
        by_action_id = {row.action_id: row for row in rows}

        items: list[dict[str, Any]] = []
        for agent_id in agent_ids:
            row = by_action_id.get(agent_id)
            extra = dict(row.extra_config or {}) if row is not None else {}
            override, _, _ = self._read_override_metadata(extra)
            definition_cache_key = self._definition_cache_key(tenant_uuid=tenant_uuid, agent_id=agent_id)
            action_cache_key = self._action_cache_key(tenant_uuid=tenant_uuid, agent_id=agent_id)

            items.append(
                {
                    "agent_id": agent_id,
                    "has_override": bool(override),
                    "is_enabled": (bool(row.is_enabled) if row is not None else None),
                    "definition_cached": bool(redis_client.client.exists(definition_cache_key)),
                    "action_cached": bool(redis_client.client.exists(action_cache_key)),
                }
            )

        return items

    def get_definition(self, *, db: Session, tenant_id: str, agent_id: str) -> dict[str, Any]:
        tenant_uuid = self._parse_tenant_uuid(tenant_id)
        normalized_agent_id = self._normalize_agent_id(agent_id)
        base_definition = self._load_base_definition_or_error(normalized_agent_id)

        row = db.scalar(
            select(AgenticActionConfigModel)
            .where(AgenticActionConfigModel.tenant_id == str(tenant_uuid))
            .where(AgenticActionConfigModel.action_id == normalized_agent_id)
        )
        extra = dict(row.extra_config or {}) if row is not None else {}
        override, updated_by, updated_at = self._read_override_metadata(extra)

        merged = self._loader._deep_merge_allowed(base=base_definition, overrides=override)
        definition = self._validate_merged_definition(merged)

        definition_cache_key = self._definition_cache_key(tenant_uuid=tenant_uuid, agent_id=normalized_agent_id)
        action_cache_key = self._action_cache_key(tenant_uuid=tenant_uuid, agent_id=normalized_agent_id)

        return {
            "tenant_id": str(tenant_uuid),
            "agent_id": normalized_agent_id,
            "definition": definition.model_dump(by_alias=True, mode="json"),
            "has_override": bool(override),
            "override": override if override else None,
            "override_updated_by": updated_by,
            "override_updated_at": updated_at,
            "is_enabled": (bool(row.is_enabled) if row is not None else None),
            "cache_key_state": {
                "definition_key": definition_cache_key,
                "action_key": action_cache_key,
                "definition_cached": bool(redis_client.client.exists(definition_cache_key)),
                "action_cached": bool(redis_client.client.exists(action_cache_key)),
            },
        }

    def upsert_override(
        self,
        *,
        db: Session,
        tenant_id: str,
        agent_id: str,
        override_payload: dict[str, Any],
        updated_by: str,
    ) -> dict[str, Any]:
        tenant_uuid = self._parse_tenant_uuid(tenant_id)
        normalized_agent_id = self._normalize_agent_id(agent_id)
        base_definition = self._load_base_definition_or_error(normalized_agent_id)

        normalized_updated_by = str(updated_by or "").strip()
        if not normalized_updated_by:
            raise ValidationError(
                message="updated_by is required",
                code="AGENT_DEFINITION_OVERRIDE_INVALID",
            )

        normalized_override = self._normalize_override_payload(
            override_payload=override_payload,
            base_definition=base_definition,
        )

        row = db.scalar(
            select(AgenticActionConfigModel)
            .where(AgenticActionConfigModel.tenant_id == str(tenant_uuid))
            .where(AgenticActionConfigModel.action_id == normalized_agent_id)
        )
        if row is None:
            raise ValidationError(
                message=(
                    "Agent action configuration not found for "
                    f"tenant={tenant_uuid} action={normalized_agent_id}"
                ),
                code="AGENT_ACTION_CONFIG_NOT_FOUND",
            )

        merged = self._loader._deep_merge_allowed(base=base_definition, overrides=normalized_override)
        definition = self._validate_merged_definition(merged)

        updated_at = datetime.now(tz=UTC).isoformat()
        extra = dict(row.extra_config or {})
        extra[self._OVERRIDE_KEY] = normalized_override
        extra[self._UPDATED_BY_KEY] = normalized_updated_by
        extra[self._UPDATED_AT_KEY] = updated_at
        row.extra_config = extra

        db.add(row)
        db.commit()
        db.refresh(row)

        cache_invalidation = self.invalidate_cache(
            tenant_id=str(tenant_uuid),
            agent_ids=[normalized_agent_id],
            include_action_cache=True,
        )

        return {
            "tenant_id": str(tenant_uuid),
            "agent_id": normalized_agent_id,
            "override": normalized_override,
            "override_updated_by": normalized_updated_by,
            "override_updated_at": updated_at,
            "is_enabled": bool(row.is_enabled),
            "definition": definition.model_dump(by_alias=True, mode="json"),
            "cache_invalidation": cache_invalidation,
        }

    def delete_override(self, *, db: Session, tenant_id: str, agent_id: str) -> dict[str, Any]:
        tenant_uuid = self._parse_tenant_uuid(tenant_id)
        normalized_agent_id = self._normalize_agent_id(agent_id)
        self._load_base_definition_or_error(normalized_agent_id)

        row = db.scalar(
            select(AgenticActionConfigModel)
            .where(AgenticActionConfigModel.tenant_id == str(tenant_uuid))
            .where(AgenticActionConfigModel.action_id == normalized_agent_id)
        )
        if row is None:
            raise ValidationError(
                message=f"No override found for agent {normalized_agent_id}",
                code="AGENT_DEFINITION_OVERRIDE_NOT_FOUND",
            )

        extra = dict(row.extra_config or {})
        if not isinstance(extra.get(self._OVERRIDE_KEY), dict):
            raise ValidationError(
                message=f"No override found for agent {normalized_agent_id}",
                code="AGENT_DEFINITION_OVERRIDE_NOT_FOUND",
            )

        extra.pop(self._OVERRIDE_KEY, None)
        extra.pop(self._UPDATED_BY_KEY, None)
        extra.pop(self._UPDATED_AT_KEY, None)
        row.extra_config = extra

        db.add(row)
        db.commit()
        db.refresh(row)

        cache_invalidation = self.invalidate_cache(
            tenant_id=str(tenant_uuid),
            agent_ids=[normalized_agent_id],
            include_action_cache=True,
        )

        return {
            "tenant_id": str(tenant_uuid),
            "agent_id": normalized_agent_id,
            "deleted": True,
            "cache_invalidation": cache_invalidation,
        }

    def invalidate_cache(
        self,
        *,
        tenant_id: str,
        agent_ids: list[str] | None = None,
        include_action_cache: bool = True,
    ) -> dict[str, Any]:
        tenant_uuid = self._parse_tenant_uuid(tenant_id)

        if agent_ids is not None:
            normalized_agent_ids = self._normalize_agent_ids(agent_ids)
            definition_keys = [
                self._definition_cache_key(tenant_uuid=tenant_uuid, agent_id=agent_id)
                for agent_id in normalized_agent_ids
            ]
            action_keys = [
                self._action_cache_key(tenant_uuid=tenant_uuid, agent_id=agent_id)
                for agent_id in normalized_agent_ids
            ]

            deleted_definition_keys = redis_client.client.delete(*definition_keys) if definition_keys else 0
            deleted_action_keys = 0
            if include_action_cache and action_keys:
                deleted_action_keys = redis_client.client.delete(*action_keys)

            return {
                "deleted_definition_keys": int(deleted_definition_keys),
                "deleted_action_keys": int(deleted_action_keys),
                "requested_agent_ids": normalized_agent_ids,
            }

        definition_pattern = f"agentic:def:{tenant_uuid}:*"
        action_pattern = f"agentic:action:{tenant_uuid}:*"

        deleted_definition_keys = self._scan_delete(pattern=definition_pattern)
        deleted_action_keys = self._scan_delete(pattern=action_pattern) if include_action_cache else 0

        return {
            "deleted_definition_keys": int(deleted_definition_keys),
            "deleted_action_keys": int(deleted_action_keys),
            "requested_agent_ids": None,
        }

    def _load_base_definition_or_error(self, agent_id: str) -> dict[str, Any]:
        payload = self._loader._load_base_from_filesystem(agent_id)
        if payload is None:
            raise ValidationError(
                message=f"Agent definition not found: {agent_id}",
                code="AGENT_DEFINITION_NOT_FOUND",
            )
        return payload

    def _normalize_override_payload(
        self,
        *,
        override_payload: dict[str, Any],
        base_definition: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(override_payload, dict) or not override_payload:
            raise ValidationError(
                message="override_payload must be a non-empty JSON object",
                code="AGENT_DEFINITION_OVERRIDE_INVALID",
            )

        try:
            encoded = json.dumps(override_payload, ensure_ascii=True, sort_keys=True)
            normalized = json.loads(encoded)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="override_payload must be JSON-serializable",
                code="AGENT_DEFINITION_OVERRIDE_INVALID",
            ) from exc

        if not isinstance(normalized, dict) or not normalized:
            raise ValidationError(
                message="override_payload must be a non-empty JSON object",
                code="AGENT_DEFINITION_OVERRIDE_INVALID",
            )

        allowed_paths = self._tenant_overridable_paths(base_definition)
        if not any(self._path_exists(normalized, path) for path in allowed_paths):
            raise ValidationError(
                message=(
                    "override_payload must include at least one path from "
                    "metadata.tenant_overridable_fields"
                ),
                code="AGENT_DEFINITION_OVERRIDE_INVALID",
            )

        return normalized

    def _validate_merged_definition(self, payload: dict[str, Any]):
        try:
            return self._schema_validator.validate(payload)
        except AgentDefinitionValidationError as exc:
            raise ValidationError(
                message=f"Merged agent definition is invalid: {exc}",
                code="AGENT_DEFINITION_INVALID",
            ) from exc

    @staticmethod
    def _tenant_overridable_paths(base_definition: dict[str, Any]) -> list[str]:
        metadata = base_definition.get("metadata")
        if not isinstance(metadata, dict):
            return []

        raw_paths = metadata.get("tenant_overridable_fields")
        if not isinstance(raw_paths, list):
            return []

        return [item.strip() for item in raw_paths if isinstance(item, str) and item.strip()]

    @staticmethod
    def _path_exists(payload: dict[str, Any], dotted_path: str) -> bool:
        current: Any = payload
        for segment in dotted_path.split("."):
            if not isinstance(current, dict) or segment not in current:
                return False
            current = current[segment]
        return True

    @classmethod
    def _read_override_metadata(cls, payload: dict[str, Any]) -> tuple[dict[str, Any], str | None, str | None]:
        raw_override = payload.get(cls._OVERRIDE_KEY)
        override = dict(raw_override) if isinstance(raw_override, dict) else {}

        raw_updated_by = payload.get(cls._UPDATED_BY_KEY)
        updated_by = raw_updated_by if isinstance(raw_updated_by, str) else None

        raw_updated_at = payload.get(cls._UPDATED_AT_KEY)
        updated_at = raw_updated_at if isinstance(raw_updated_at, str) else None

        return override, updated_by, updated_at

    def _definition_cache_key(self, *, tenant_uuid: UUID, agent_id: str) -> str:
        return self._loader._cache_key(tenant_id=tenant_uuid, agent_id=agent_id)

    @staticmethod
    def _action_cache_key(*, tenant_uuid: UUID, agent_id: str) -> str:
        return f"agentic:action:{tenant_uuid}:{agent_id}"

    @staticmethod
    def _normalize_agent_id(agent_id: str) -> str:
        normalized = str(agent_id or "").strip()
        if not normalized:
            raise ValidationError(
                message="agent_id is required",
                code="AGENT_DEFINITION_NOT_FOUND",
            )
        return normalized

    @staticmethod
    def _normalize_agent_ids(agent_ids: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()

        for raw in agent_ids:
            token = str(raw or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)

        return normalized

    @staticmethod
    def _parse_tenant_uuid(tenant_id: str) -> UUID:
        try:
            return UUID(str(tenant_id).strip())
        except (TypeError, ValueError, AttributeError) as exc:
            raise ValidationError(
                message="tenant_id must be a valid UUID",
                code="TENANT_ID_INVALID",
            ) from exc

    @staticmethod
    def _scan_delete(*, pattern: str) -> int:
        deleted = 0
        cursor = 0
        while True:
            cursor, keys = redis_client.client.scan(cursor=int(cursor), match=pattern, count=200)
            if keys:
                deleted += redis_client.client.delete(*keys)
            if int(cursor) == 0:
                break
        return deleted


agent_definition_override_service = AgentDefinitionOverrideService()
