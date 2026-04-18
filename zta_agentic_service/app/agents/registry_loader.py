from __future__ import annotations

import inspect
import json
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.base_handler import BaseAgentHandler
from app.agents.handlers import HANDLER_REGISTRY
from app.db.agent_models import AgentInstance, AgentTemplate


class AgentRegistryLoader:
    """Resolves handler + tenant instance mappings with lightweight Redis caching."""

    CACHE_TTL = 300

    def __init__(
        self,
        db_session: Session,
        cache_client: Any | None = None,
        handler_dependencies: dict[str, Any] | None = None,
    ) -> None:
        self.db = db_session
        self.cache = cache_client
        self.handler_dependencies = handler_dependencies or {}

    async def get_handler_for_intent(
        self,
        intent: str,
        tenant_id: str,
        user_persona: str,
    ) -> tuple[BaseAgentHandler, AgentInstance] | None:
        instances = await self._get_tenant_instances(tenant_id)

        for instance in instances:
            template = self._get_template(instance.agent_definition_id)
            if template is None:
                continue
            if not template.is_active or not instance.is_enabled:
                continue
            if template.allowed_personas and user_persona not in template.allowed_personas:
                continue
            if self._intent_matches(intent, template):
                handler = self.instantiate_handler_by_class(template.handler_class)
                return handler, instance

        return None

    async def get_instance_for_template(self, tenant_id: str, template_id: str) -> AgentInstance | None:
        tenant_uuid = self._to_uuid(tenant_id)
        template = self._get_template(template_id)
        if template is None:
            return None

        stmt = select(AgentInstance).where(
            AgentInstance.tenant_id == tenant_uuid,
            AgentInstance.agent_definition_id == template.id,
            AgentInstance.is_enabled.is_(True),
        )
        return self.db.scalar(stmt)

    def instantiate_handler_by_class(self, handler_class: str) -> BaseAgentHandler:
        handler_type = HANDLER_REGISTRY.get(handler_class)
        if handler_type is None:
            raise KeyError(f"Unknown handler class: {handler_class}")

        signature = inspect.signature(handler_type.__init__)
        kwargs: dict[str, Any] = {}
        for name, parameter in signature.parameters.items():
            if name == "self":
                continue
            if parameter.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                continue
            if name in self.handler_dependencies:
                kwargs[name] = self.handler_dependencies[name]
            elif parameter.default is inspect._empty:
                kwargs[name] = None
        return handler_type(**kwargs)

    async def _get_tenant_instances(self, tenant_id: str) -> list[AgentInstance]:
        tenant_uuid = self._to_uuid(tenant_id)
        cache_key = f"agent_instances:{tenant_id}"

        cached_ids: list[str] | None = None
        cached_payload = await self._cache_get(cache_key)
        if cached_payload:
            try:
                decoded = json.loads(cached_payload)
                if isinstance(decoded, list):
                    cached_ids = [str(item) for item in decoded]
            except json.JSONDecodeError:
                cached_ids = None

        if cached_ids:
            stmt = select(AgentInstance).where(
                AgentInstance.id.in_([self._to_uuid(value) for value in cached_ids]),
                AgentInstance.is_enabled.is_(True),
            )
            return self.db.scalars(stmt).all()

        stmt = select(AgentInstance).where(
            AgentInstance.tenant_id == tenant_uuid,
            AgentInstance.is_enabled.is_(True),
        )
        instances = self.db.scalars(stmt).all()
        await self._cache_set(
            cache_key,
            json.dumps([str(instance.id) for instance in instances]),
            self.CACHE_TTL,
        )
        return instances

    def _get_template(self, template_id: str | uuid.UUID) -> AgentTemplate | None:
        if isinstance(template_id, uuid.UUID):
            return self.db.get(AgentTemplate, template_id)

        try:
            template_uuid = uuid.UUID(template_id)
            template = self.db.get(AgentTemplate, template_uuid)
            if template is not None:
                return template
        except ValueError:
            pass

        candidates = self._agent_key_candidates(str(template_id))
        for candidate in candidates:
            stmt = select(AgentTemplate).where(AgentTemplate.agent_key == candidate)
            row = self.db.scalar(stmt)
            if row is not None:
                return row

        lowered_candidates = [candidate.lower() for candidate in candidates]
        stmt = select(AgentTemplate).where(func.lower(AgentTemplate.agent_key).in_(lowered_candidates))
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
    def _intent_matches(intent: str, template: AgentTemplate) -> bool:
        intent_text = (intent or "").lower().strip()
        if not intent_text:
            return False

        keywords = [str(word).lower() for word in (template.trigger_config or {}).get("keywords", [])]
        if any(keyword and keyword in intent_text for keyword in keywords):
            return True

        return any(
            value in intent_text
            for value in [
                (template.agent_key or "").lower(),
                (template.name or "").lower(),
                (template.domain or "").lower(),
            ]
            if value
        )

    async def invalidate_tenant_cache(self, tenant_id: str) -> None:
        if self.cache is None:
            return
        result = self.cache.delete(f"agent_instances:{tenant_id}")
        if inspect.isawaitable(result):
            await result

    async def _cache_get(self, key: str) -> str | None:
        if self.cache is None:
            return None
        result = self.cache.get(key)
        if inspect.isawaitable(result):
            result = await result
        if result is None:
            return None
        return str(result)

    async def _cache_set(self, key: str, value: str, ttl_seconds: int) -> None:
        if self.cache is None:
            return
        result = self.cache.setex(key, ttl_seconds, value)
        if inspect.isawaitable(result):
            await result

    @staticmethod
    def _to_uuid(value: str) -> uuid.UUID:
        return uuid.UUID(str(value))
