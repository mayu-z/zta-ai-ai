from __future__ import annotations

import asyncio
import hashlib
from abc import ABC, abstractmethod
from uuid import uuid4

from app.agentic.core.action_registry import ActionRegistry
from app.agentic.core.approval_layer import ApprovalLayer
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.compiler_interface import CompilerInterface, ExecutionPlan
from app.agentic.core.notification_dispatcher import NotificationDispatcher
from app.agentic.core.policy_engine import PolicyEngine
from app.agentic.core.scope_guard import ScopeGuard, ScopeViolation
from app.agentic.core.sensitive_field_monitor import SensitiveFieldMonitor
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import AgentResult, AgentStatus, ClaimSet, IntentClassification, RequestContext
from app.agentic.models.audit_event import AuditEvent
from app.agentic.models.sensitive_event import SensitiveAccessEvent


def generate_audit_id() -> str:
    return f"audit_{uuid4().hex}"


class BaseAgent(ABC):
    """Base class enforcing the fixed agentic pipeline."""

    def __init__(
        self,
        action_registry: ActionRegistry,
        policy_engine: PolicyEngine,
        scope_guard: ScopeGuard,
        compiler: CompilerInterface,
        audit_logger: AuditLogger,
        sensitive_monitor: SensitiveFieldMonitor,
        notification_dispatcher: NotificationDispatcher,
        approval_layer: ApprovalLayer,
    ):
        self._registry = action_registry
        self._policy = policy_engine
        self._scope = scope_guard
        self._compiler = compiler
        self._audit = audit_logger
        self._monitor = sensitive_monitor
        self._notifications = notification_dispatcher
        self._approval = approval_layer

    async def run(
        self,
        intent: IntentClassification,
        ctx: RequestContext,
    ) -> AgentResult:
        audit_id = generate_audit_id()
        result = AgentResult(
            status=AgentStatus.FAILED,
            message="",
            audit_event_id=audit_id,
        )
        action: ActionConfig | None = None

        try:
            action = await self._registry.get(intent.action_id, ctx.tenant_id)
            if not action or not action.is_enabled:
                result = AgentResult(
                    status=AgentStatus.FALLBACK_TO_INFO,
                    message="No matching action found.",
                    audit_event_id=audit_id,
                )
                return result

            policy_decision = await self._policy.evaluate(action, ctx)
            if not policy_decision.allowed:
                await self._audit.write(
                    AuditEvent(
                        event_type="PERMISSION_DENIED",
                        action_id=action.action_id,
                        user_alias=ctx.user_alias,
                        tenant_id=ctx.tenant_id,
                        status="DENIED",
                        metadata={"reason": policy_decision.denial_reason or "not allowed"},
                    )
                )
                result = AgentResult(
                    status=AgentStatus.PERMISSION_DENIED,
                    message=policy_decision.denial_reason or "Permission denied",
                    audit_event_id=audit_id,
                )
                return result

            try:
                claim_set = await self._scope.fetch_scoped(action, ctx)
            except ScopeViolation as exc:
                await self._audit.write(
                    AuditEvent(
                        event_type="SCOPE_VIOLATION",
                        action_id=action.action_id,
                        user_alias=ctx.user_alias,
                        tenant_id=ctx.tenant_id,
                        status="BLOCKED",
                        metadata={"violation": str(exc)},
                    )
                )
                result = AgentResult(
                    status=AgentStatus.SCOPE_DENIED,
                    message="Access denied: data outside your scope.",
                    audit_event_id=audit_id,
                )
                return result

            if action.has_sensitive_fields:
                asyncio.create_task(
                    self._monitor.emit(
                        SensitiveAccessEvent(
                            user_alias=ctx.user_alias,
                            session_id=ctx.session_id,
                            tenant_id=ctx.tenant_id,
                            persona=ctx.persona,
                            department=ctx.department_id,
                            fields_accessed=list(claim_set.claims.keys()),
                            field_classifications=claim_set.field_classifications,
                            data_subject_alias=str(claim_set.claims.get("subject_alias", "own")),
                            result_row_count=claim_set.row_count,
                            query_type=action.action_id,
                        )
                    )
                )

            approval = await self._approval.evaluate(action, claim_set, ctx)
            if not approval.approved:
                await self._audit.write(
                    AuditEvent(
                        event_type="ACTION_CANCELLED",
                        action_id=action.action_id,
                        user_alias=ctx.user_alias,
                        tenant_id=ctx.tenant_id,
                        status="CANCELLED",
                        metadata={"reason": approval.cancellation_reason or "cancelled"},
                    )
                )
                result = AgentResult(
                    status=AgentStatus.CANCELLED,
                    message="Action cancelled.",
                    audit_event_id=audit_id,
                    metadata=approval.metadata,
                )
                return result

            execution_plan = await self._compiler.build_plan(action, claim_set, approval, ctx)
            result = await self.execute(action, claim_set, execution_plan, ctx)
            if result.audit_event_id is None:
                result.audit_event_id = audit_id

        except Exception as exc:  # noqa: BLE001
            result = AgentResult(
                status=AgentStatus.FAILED,
                message=f"Execution error: {type(exc).__name__}",
                audit_event_id=audit_id,
            )

        finally:
            await self._audit.write(
                AuditEvent(
                    event_type="AGENTIC_ACTION",
                    action_id=(intent.action_id or (action.action_id if action else "unknown")),
                    user_alias=ctx.user_alias,
                    tenant_id=ctx.tenant_id,
                    status=result.status.value,
                    payload_hash=(
                        hashlib.sha256(str(result.data).encode()).hexdigest()
                        if result.data is not None
                        else None
                    ),
                    metadata={"workflow_id": result.workflow_id},
                )
            )

        if result.status == AgentStatus.SUCCESS and action and action.notification_config:
            await self._notifications.dispatch(action.notification_config, result, ctx)

        return result

    @abstractmethod
    async def execute(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        execution_plan: ExecutionPlan,
        ctx: RequestContext,
    ) -> AgentResult:
        ...
