from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from app.agentic.agents.bulk_notification import BulkNotificationAgent
from app.agentic.agents.email_draft import EmailDraftAgent
from app.agentic.agents.email_send import EmailSendAgent
from app.agentic.agents.fee_reminder import FeeReminderAgent
from app.agentic.agents.leave_approval import LeaveApprovalAgent
from app.agentic.agents.leave_balance import LeaveBalanceAgent
from app.agentic.agents.meeting_scheduler import MeetingSchedulerAgent
from app.agentic.agents.payroll_query import PayrollQueryAgent
from app.agentic.agents.refund import RefundAgent
from app.agentic.agents.result_notification import ResultNotificationAgent
from app.agentic.agents.upi_payment import UPIPaymentAgent
from app.agentic.compiler.execution_planner import ExecutionPlanner
from app.agentic.compiler.scope_injector import ScopeInjector
from app.agentic.compiler.write_guard import WriteGuard
from app.agentic.connectors.claimset_builder import ClaimSetBuilder, MaskingEngine, SchemaRegistry
from app.agentic.connectors.registry import ConnectorPool
from app.agentic.connectors.router import ConnectorRouter, TenantConfigService
from app.agentic.core.action_registry import ActionRegistry
from app.agentic.core.approval_layer import ApprovalLayer
from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.compiler_interface import CompilerInterface
from app.agentic.core.intent_classifier import IntentClassifier
from app.agentic.core.notification_dispatcher import NotificationDispatcher
from app.agentic.core.policy_engine import PolicyEngine
from app.agentic.core.scope_guard import ScopeGuard
from app.agentic.core.sensitive_field_monitor import SensitiveFieldMonitor
from app.agentic.models.agent_context import AgentStatus, RequestContext
from app.core.exceptions import AuthorizationError
from app.schemas.pipeline import ScopeContext


@dataclass(frozen=True)
class AgenticExecutionOutcome:
    response_text: str
    source: str
    intent_hash: str
    domains_accessed: list[str]
    was_blocked: bool
    block_reason: str | None


class AgenticRuntimeBridge:
    def __init__(self) -> None:
        self._classifier = IntentClassifier()
        self._registry = ActionRegistry()
        self._audit_logger = AuditLogger()
        planner = ExecutionPlanner(
            scope_injector=ScopeInjector(),
            connector_router=ConnectorRouter(ConnectorPool(), TenantConfigService()),
            claimset_builder=ClaimSetBuilder(SchemaRegistry(), MaskingEngine()),
            write_guard=WriteGuard(),
            audit_logger=self._audit_logger,
        )
        compiler = CompilerInterface(planner=planner)

        self._policy = PolicyEngine()
        self._scope = ScopeGuard(compiler=compiler)
        self._compiler = compiler
        self._monitor = SensitiveFieldMonitor()
        self._notifications = NotificationDispatcher()
        self._approval = ApprovalLayer()

    @staticmethod
    def _run_async(coro: Any) -> Any:
        with ThreadPoolExecutor(max_workers=1) as executor:
            return executor.submit(lambda: asyncio.run(coro)).result()

    @staticmethod
    def _action_domains(required_data_scope: list[str]) -> list[str]:
        domains = {descriptor.split(".", 1)[0].strip() for descriptor in required_data_scope if descriptor.strip()}
        return sorted(domain for domain in domains if domain)

    def _build_request_context(self, scope: ScopeContext) -> RequestContext:
        return RequestContext(
            tenant_id=scope.tenant_id,
            user_alias=scope.external_id or scope.user_id,
            session_id=scope.session_id,
            persona=scope.persona_type,
            department_id=scope.department or "",
            jwt_claims={
                "tenant_id": scope.tenant_id,
                "role_key": scope.role_key or "",
                "admin_function": scope.admin_function or "",
            },
        )

    def _build_agent(self, action_id: str):
        common_kwargs = {
            "action_registry": self._registry,
            "policy_engine": self._policy,
            "scope_guard": self._scope,
            "compiler": self._compiler,
            "audit_logger": self._audit_logger,
            "sensitive_monitor": self._monitor,
            "notification_dispatcher": self._notifications,
            "approval_layer": self._approval,
        }

        mapping = {
            "result_notification_v1": ResultNotificationAgent,
            "fee_reminder_v1": FeeReminderAgent,
            "upi_payment_link_v1": UPIPaymentAgent,
            "refund_request_v1": RefundAgent,
            "email_draft_v1": EmailDraftAgent,
            "email_send_v1": EmailSendAgent,
            "bulk_notification_v1": BulkNotificationAgent,
            "leave_approval_v1": LeaveApprovalAgent,
            "meeting_scheduler_v1": MeetingSchedulerAgent,
            "payroll_query_v1": PayrollQueryAgent,
            "leave_balance_check_v1": LeaveBalanceAgent,
            "leave_balance_apply_v1": LeaveBalanceAgent,
        }
        agent_cls = mapping.get(action_id)
        if agent_cls is None:
            return None
        return agent_cls(**common_kwargs)

    def maybe_execute(self, *, query_text: str, scope: ScopeContext) -> AgenticExecutionOutcome | None:
        classification = self._run_async(self._classifier.classify(query_text))
        if not classification.is_agentic or not classification.action_id:
            return None

        action = self._run_async(self._registry.get(classification.action_id, scope.tenant_id))
        if action is None or not action.is_enabled:
            return None

        agent = self._build_agent(action.action_id)
        if agent is None:
            return None

        ctx = self._build_request_context(scope)
        result = self._run_async(agent.run(classification, ctx))
        domains = self._action_domains(action.required_data_scope)

        if result.status == AgentStatus.SUCCESS:
            return AgenticExecutionOutcome(
                response_text=result.message,
                source="agentic",
                intent_hash=f"agentic:{classification.action_id}",
                domains_accessed=domains,
                was_blocked=False,
                block_reason=None,
            )

        if result.status in {AgentStatus.PERMISSION_DENIED, AgentStatus.SCOPE_DENIED}:
            raise AuthorizationError(
                message=result.message or "Agentic action denied",
                code=result.status.value,
            )

        if result.status == AgentStatus.CANCELLED:
            return AgenticExecutionOutcome(
                response_text=result.message or "Action requires confirmation.",
                source="agentic",
                intent_hash=f"agentic:{classification.action_id}",
                domains_accessed=domains,
                was_blocked=True,
                block_reason="CONFIRMATION_REQUIRED",
            )

        return AgenticExecutionOutcome(
            response_text=result.message or "Agentic action failed.",
            source="agentic",
            intent_hash=f"agentic:{classification.action_id}",
            domains_accessed=domains,
            was_blocked=True,
            block_reason=result.status.value,
        )


agentic_runtime_bridge = AgenticRuntimeBridge()
