from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.agentic.db_models import AgenticActionConfigModel
from app.agentic.models.agent_definition import AgentDefinition
from app.agentic.registry.schema_validator import AgentDefinitionSchemaValidator
from app.core.redis_client import redis_client
from app.db.session import SessionLocal


class AgentDefinitionLoader:
    def __init__(
        self,
        definitions_dir: Path | None = None,
        cache_ttl_seconds: int = 300,
        schema_validator: AgentDefinitionSchemaValidator | None = None,
    ) -> None:
        self._definitions_dir = definitions_dir or (Path(__file__).resolve().parent.parent / "definitions")
        self._cache_ttl_seconds = cache_ttl_seconds
        self._schema_validator = schema_validator or AgentDefinitionSchemaValidator()

    def _cache_key(self, *, tenant_id: UUID, agent_id: str) -> str:
        return f"agentic:def:{tenant_id}:{agent_id}"

    async def load(self, agent_id: str, tenant_id: UUID) -> AgentDefinition | None:
        cache_key = self._cache_key(tenant_id=tenant_id, agent_id=agent_id)
        cached = redis_client.client.get(cache_key)
        if cached:
            return AgentDefinition.model_validate_json(cached)

        base = self._load_base_from_filesystem(agent_id)
        if base is None:
            return None

        override = await asyncio.to_thread(self._load_tenant_override_sync, agent_id, tenant_id)
        merged = self._deep_merge_allowed(base=base, overrides=override)
        validated = self._schema_validator.validate(merged)
        redis_client.client.setex(cache_key, self._cache_ttl_seconds, validated.model_dump_json(by_alias=True))
        return validated

    async def list_available(self, tenant_id: UUID) -> list[str]:
        names = sorted(path.stem for path in self._definitions_dir.glob("*.json"))
        disabled = await asyncio.to_thread(self._list_disabled_sync, tenant_id)
        return [item for item in names if item not in disabled]

    async def invalidate_cache(self, agent_id: str, tenant_id: UUID) -> None:
        redis_client.client.delete(self._cache_key(tenant_id=tenant_id, agent_id=agent_id))

    def _load_base_from_filesystem(self, agent_id: str) -> dict[str, Any] | None:
        path = self._definitions_dir / f"{agent_id}.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def _load_tenant_override_sync(self, agent_id: str, tenant_id: UUID) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticActionConfigModel)
                .where(AgenticActionConfigModel.tenant_id == str(tenant_id))
                .where(AgenticActionConfigModel.action_id == agent_id)
            )
            if row is None:
                return {}

            extra = dict(row.extra_config or {})
            override = extra.get("agent_definition_override")
            if isinstance(override, dict):
                return override
            return {}
        finally:
            db.close()

    def _list_disabled_sync(self, tenant_id: UUID) -> set[str]:
        db = SessionLocal()
        try:
            rows = db.scalars(
                select(AgenticActionConfigModel)
                .where(AgenticActionConfigModel.tenant_id == str(tenant_id))
                .where(AgenticActionConfigModel.is_enabled.is_(False))
            ).all()
            return {row.action_id for row in rows}
        finally:
            db.close()

    def _deep_merge_allowed(self, *, base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        if not overrides:
            return dict(base)

        merged = json.loads(json.dumps(base))
        allowlist = base.get("metadata", {}).get("tenant_overridable_fields", [])
        if not isinstance(allowlist, list):
            return merged

        for raw_path in allowlist:
            if not isinstance(raw_path, str) or not raw_path.strip():
                continue
            path = raw_path.strip()
            override_value = self._get_path(overrides, path)
            if override_value is None:
                continue
            self._set_path(merged, path, override_value)

        return merged

    @staticmethod
    def _get_path(payload: dict[str, Any], dotted_path: str) -> Any:
        current: Any = payload
        for segment in dotted_path.split("."):
            if not isinstance(current, dict):
                return None
            if segment not in current:
                return None
            current = current[segment]
        return current

    @staticmethod
    def _set_path(payload: dict[str, Any], dotted_path: str, value: Any) -> None:
        parts = dotted_path.split(".")
        current = payload
        for segment in parts[:-1]:
            if segment not in current or not isinstance(current[segment], dict):
                current[segment] = {}
            current = current[segment]
        current[parts[-1]] = value
