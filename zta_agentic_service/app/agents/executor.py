from __future__ import annotations

import uuid
from datetime import UTC, datetime
from time import perf_counter
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from app.agents.base_handler import AgentContext, AgentResult

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.agents.registry_loader import AgentRegistryLoader
    from app.db.agent_models import AgentInstance, AgentTemplate
else:
    Session = Any
    AgentRegistryLoader = Any
    AgentInstance = Any
    AgentTemplate = Any


class AgentExecutor:
    """Executes registry-driven handlers with zero-trust guards and immutable logging."""

    def __init__(self, db_session: Session, loader: AgentRegistryLoader) -> None:
        self.db = db_session
        self.loader = loader

    async def execute_action(
        self,
        *,
        tenant_id: str,
        template_id: str,
        user_id: str | None,
        user_persona: str,
        trigger_payload: dict[str, Any],
        claim_set: dict[str, Any],
        confirmed: bool = False,
        action_id: str | None = None,
    ) -> AgentResult:
        started = perf_counter()
        action_identifier = action_id or str(uuid.uuid4())

        instance = await self.loader.get_instance_for_template(tenant_id=tenant_id, template_id=template_id)
        if instance is None:
            return self._with_action_id(
                AgentResult(
                    status="failed",
                    output={},
                    error=(
                        f"No enabled instance found for template '{template_id}' and tenant '{tenant_id}'."
                    ),
                ),
                action_identifier,
            )

        try:
            template_model = self._agent_template_model()
        except Exception:
            template_model = None
        template = self.db.get(template_model, instance.agent_definition_id)
        if template is None or not template.is_active:
            return self._with_action_id(
                AgentResult(status="failed", output={}, error="Agent template is not active"),
                action_identifier,
            )

        if template.allowed_personas and user_persona not in template.allowed_personas:
            return self._with_action_id(
                AgentResult(
                    status="failed",
                    output={},
                    error=(
                        f"Persona '{user_persona}' is not allowed to execute '{template.template_id}'."
                    ),
                ),
                action_identifier,
            )

        dependency_error = await self._check_dependencies(instance, template, tenant_id)
        if dependency_error:
            return self._with_action_id(
                AgentResult(status="failed", output={}, error=dependency_error),
                action_identifier,
            )

        try:
            handler = self.loader.instantiate_handler_by_class(template.handler_class)
        except KeyError as exc:
            return self._with_action_id(
                AgentResult(status="failed", output={}, error=str(exc)),
                action_identifier,
            )
        triggered_by = str(trigger_payload.get("triggered_by", "api_execute"))
        interactive_trigger = triggered_by in {"api_execute", "user_query", "ui_execute"}
        requires_confirmation = bool(template.requires_confirmation or (template.is_side_effect and interactive_trigger))
        if requires_confirmation and not confirmed:
            result = AgentResult(
                status="pending_confirmation",
                requires_confirmation=True,
                confirmation_prompt=(
                    template.confirmation_prompt
                    or f"This action may have side effects. Confirm execution of '{template.name}'."
                ),
                output={"template_id": template.template_id},
            )
            await self._append_log(
                action_id=action_identifier,
                instance=instance,
                tenant_id=tenant_id,
                user_id=user_id,
                trigger_payload=trigger_payload,
                result=result,
                started=started,
            )
            return self._with_action_id(result, action_identifier)

        context = AgentContext(
            action_id=action_identifier,
            instance=instance,
            tenant_id=tenant_id,
            user_id=user_id,
            claim_set=claim_set,
            trigger_payload=trigger_payload,
            confirmed=confirmed,
        )

        result: AgentResult
        try:
            result = await handler.execute(context)
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            result = AgentResult(
                status="failed",
                output={},
                error=f"Unhandled handler error: {exc}",
            )

        if result.status == "failed" and handler.is_side_effect:
            try:
                await handler.rollback(context, result)
                result.rollback_performed = True
            except Exception:
                result.rollback_performed = False

        await self._append_log(
            action_id=action_identifier,
            instance=instance,
            tenant_id=tenant_id,
            user_id=user_id,
            trigger_payload=trigger_payload,
            result=result,
            started=started,
        )
        return self._with_action_id(result, action_identifier)

    async def _check_dependencies(
        self,
        instance: AgentInstance,
        template: AgentTemplate,
        tenant_id: str,
    ) -> str | None:
        _ = instance
        dependencies = (template.trigger_config or {}).get("depends_on", [])
        if not dependencies:
            return None

        for dependency in dependencies:
            dep_instance = await self.loader.get_instance_for_template(
                tenant_id=tenant_id,
                template_id=str(dependency),
            )
            if dep_instance is None or not dep_instance.is_enabled:
                return (
                    f"Required dependency '{dependency}' is not enabled for tenant '{tenant_id}'."
                )
        return None

    async def _append_log(
        self,
        *,
        action_id: str,
        instance: AgentInstance,
        tenant_id: str,
        user_id: str | None,
        trigger_payload: dict[str, Any],
        result: AgentResult,
        started: float,
    ) -> None:
        completed_at = datetime.now(UTC)
        elapsed_ms = int((perf_counter() - started) * 1000)

        payload = {
            "instance_id": instance.id,
            "tenant_id": self._to_uuid(tenant_id),
            "triggered_by": str(trigger_payload.get("triggered_by", "api_execute")),
            "user_id": user_id,
            "action_id": action_id,
            "status": result.status,
            "execution_ms": max(elapsed_ms, 0),
            "input_summary": {
                "query": trigger_payload.get("query"),
                "intent": trigger_payload.get("intent"),
                "confirmed": trigger_payload.get("confirmed", False),
            },
            "output_summary": result.output,
            "error_detail": result.error,
            "created_at": completed_at,
        }
        try:
            log_model = self._agent_execution_log_model()
        except Exception:
            log_model = None
        log = log_model(**payload) if callable(log_model) else SimpleNamespace(**payload)

        instance.last_triggered_at = completed_at
        instance.trigger_count = int(instance.trigger_count or 0) + 1

        self.db.add(log)
        self.db.add(instance)
        self.db.commit()

    @staticmethod
    def _to_uuid(value: str) -> uuid.UUID:
        return uuid.UUID(str(value))

    @staticmethod
    def _with_action_id(result: AgentResult, action_id: str) -> AgentResult:
        result.output.setdefault("action_id", action_id)
        return result

    @staticmethod
    def _agent_template_model() -> Any:
        from app.db.agent_models import AgentTemplate

        return AgentTemplate

    @staticmethod
    def _agent_execution_log_model() -> Any:
        from app.db.agent_models import AgentExecutionLog

        return AgentExecutionLog
