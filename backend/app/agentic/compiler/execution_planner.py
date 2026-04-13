from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
from typing import Any
from uuid import uuid4

from app.agentic.core.audit_logger import AuditLogger
from app.agentic.core.policy_engine import PolicyDecision
from app.agentic.models.action_config import ActionConfig
from app.agentic.models.agent_context import ClaimSet, RequestContext
from app.agentic.models.audit_event import AuditEvent
from app.agentic.models.execution_plan import ReadExecutionPlan, ScopeFilter, WriteExecutionPlan

from app.agentic.connectors.base import (
    ConnectorAuthError,
    ConnectorError,
    ConnectorTimeoutError,
    MissingScopeFilter,
    QueryInjectionAttempt,
    WriteResult,
)
from app.agentic.connectors.claimset_builder import ClaimSetBuilder
from app.agentic.connectors.router import ConnectorRouter
from app.agentic.core.compiler_interface import ExecutionPlan

from .scope_injector import ScopeInjector
from .write_guard import WriteGuard


FALLBACKS = {
    "postgres": "Data temporarily unavailable. Please try again in a few minutes.",
    "erpnext": "University ERP is not responding. Finance team has been notified.",
    "upi_gateway": "Payment link generation temporarily unavailable. Please contact the Finance Office.",
    "smtp": "Email delivery is queued and will be sent shortly.",
    "calendar": "Calendar service is unavailable. Please check availability manually.",
}


class WriteFailure(Exception):
    pass


@dataclass(frozen=True)
class ConnectorExecutionContext:
    entity: str
    plan_id: str
    tenant_id: str
    user_alias: str


def generate_plan_id() -> str:
    return f"plan_{uuid4().hex}"


class ExecutionPlanner:
    def __init__(
        self,
        scope_injector: ScopeInjector,
        connector_router: ConnectorRouter,
        claimset_builder: ClaimSetBuilder,
        write_guard: WriteGuard,
        audit_logger: AuditLogger,
    ):
        self._scope = scope_injector
        self._router = connector_router
        self._claimset_builder = claimset_builder
        self._write_guard = write_guard
        self._audit = audit_logger

    async def build_plan(
        self,
        action: ActionConfig,
        claim_set: ClaimSet,
        approval: Any,
        ctx: RequestContext,
    ) -> ExecutionPlan:
        metadata = {
            "claims": claim_set.claims,
            "field_classifications": claim_set.field_classifications,
            "approval": {
                "approved": bool(getattr(approval, "approved", False)),
                "approver_alias": getattr(approval, "approver_alias", None),
            },
            "ctx": {
                "tenant_id": str(ctx.tenant_id),
                "user_alias": ctx.user_alias,
                "persona": ctx.persona,
                "department_id": ctx.department_id,
            },
        }
        return ExecutionPlan(
            action_id=action.action_id,
            steps=["validate_write_guard", "prepare_payload", "execute"],
            write_target=action.write_target,
            payload={"claims": claim_set.claims},
            metadata=metadata,
        )

    async def fetch_data(
        self,
        action: ActionConfig,
        ctx: RequestContext,
        policy_decision: PolicyDecision,
    ) -> ClaimSet:
        merged_claims: dict[str, Any] = {}
        merged_classifications: dict[str, str] = {}
        total_rows = 0

        for descriptor in action.required_data_scope:
            entity = descriptor.split(".", 1)[0]
            scope_filter, additional_filters = self._scope.inject(action, ctx, entity)
            self._validate_scope(scope_filter)

            plan = ReadExecutionPlan(
                plan_id=generate_plan_id(),
                entity=entity,
                fields=[],
                filters=additional_filters,
                scope=scope_filter,
                limit=int(action.extra_config.get("max_rows", 100)),
                operation=str(action.extra_config.get("operation", "")) or None,
                payload=dict(action.extra_config.get("payload", {})),
            )

            execution_context = ConnectorExecutionContext(
                entity=entity,
                plan_id=plan.plan_id,
                tenant_id=str(ctx.tenant_id),
                user_alias=ctx.user_alias,
            )

            raw_result = await self._read_with_retry(plan=plan, ctx=ctx, execution_context=execution_context)
            claim_set = self._claimset_builder.build(
                raw_result=raw_result,
                entity=entity,
                tenant_id=ctx.tenant_id,
                policy_decision=policy_decision,
            )

            merged_claims.update(claim_set.claims)
            merged_classifications.update(claim_set.field_classifications)
            total_rows += raw_result.row_count

            await self._audit.write(
                AuditEvent(
                    event_type="CONNECTOR_EXECUTION",
                    action_id=action.action_id,
                    user_alias=ctx.user_alias,
                    tenant_id=ctx.tenant_id,
                    status="SUCCESS",
                    data_accessed=list(claim_set.claims.keys()),
                    metadata={
                        "plan_id": plan.plan_id,
                        "entity": entity,
                        "source_alias": raw_result.source_schema,
                        "row_count": raw_result.row_count,
                        "execution_time_ms": raw_result.execution_time_ms,
                    },
                )
            )

        return ClaimSet(
            claims=merged_claims,
            field_classifications=merged_classifications,
            source_alias="merged",
            fetched_at=datetime.now(tz=UTC).replace(tzinfo=None),
            row_count=total_rows,
        )

    async def execute_write(
        self,
        action: ActionConfig,
        payload: dict[str, Any],
        ctx: RequestContext,
    ):
        parsed = self._write_guard.validate(action_id=action.action_id, write_target=action.write_target)
        scope_filter, _ = self._scope.inject(action, ctx, parsed.entity)
        self._validate_scope(scope_filter)

        operation = parsed.operation
        if operation in {"send_email", "create_link"}:
            read_plan = ReadExecutionPlan(
                plan_id=generate_plan_id(),
                entity=parsed.entity,
                fields=[],
                filters=[],
                scope=scope_filter,
                operation=operation,
                payload=payload,
                limit=1,
            )
            raw = await self._read_with_retry(
                plan=read_plan,
                ctx=ctx,
                execution_context=ConnectorExecutionContext(
                    entity=parsed.entity,
                    plan_id=read_plan.plan_id,
                    tenant_id=str(ctx.tenant_id),
                    user_alias=ctx.user_alias,
                ),
            )
            generated_id = None
            details = None
            if raw.rows:
                details = dict(raw.rows[0])
                generated_id = str(raw.rows[0].get("order_id") or raw.rows[0].get("message_hash") or "") or None
            return WriteResult(
                rows_affected=raw.row_count,
                generated_id=generated_id,
                execution_time_ms=raw.execution_time_ms,
                details=details,
            )

        write_plan = WriteExecutionPlan(
            plan_id=generate_plan_id(),
            entity=parsed.entity,
            operation=operation,
            payload=payload,
            filters=[],
            scope=scope_filter,
            allowed_by_action_id=action.action_id,
        )

        result = await self._write_with_retry(plan=write_plan, ctx=ctx)
        expected = int(action.extra_config.get("expected_rows", 1))
        if expected > 0 and result.rows_affected == 0:
            raise WriteFailure("Write operation did not affect expected records")

        payload_hash = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
        await self._audit.write(
            AuditEvent(
                event_type="CONNECTOR_EXECUTION",
                action_id=action.action_id,
                user_alias=ctx.user_alias,
                tenant_id=ctx.tenant_id,
                status="SUCCESS",
                payload_hash=payload_hash,
                metadata={
                    "plan_id": write_plan.plan_id,
                    "entity": write_plan.entity,
                    "operation": write_plan.operation,
                    "rows_affected": result.rows_affected,
                    "execution_time_ms": result.execution_time_ms,
                },
            )
        )
        return result

    async def _read_with_retry(
        self,
        *,
        plan: ReadExecutionPlan,
        ctx: RequestContext,
        execution_context: ConnectorExecutionContext,
    ):
        delays = [0, 1, 3]
        last_timeout: ConnectorTimeoutError | None = None

        for delay in delays:
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._router.route_read(plan, ctx.tenant_id)
            except ConnectorTimeoutError as exc:
                last_timeout = exc
                continue
            except (MissingScopeFilter, QueryInjectionAttempt):
                raise
            except (ConnectorAuthError, ConnectorError):
                raise

        assert last_timeout is not None
        await self._audit.write(
            AuditEvent(
                event_type="CONNECTOR_TIMEOUT",
                action_id=execution_context.entity,
                user_alias=execution_context.user_alias,
                tenant_id=ctx.tenant_id,
                status="FAILED",
                metadata={"plan_id": execution_context.plan_id, "entity": execution_context.entity},
            )
        )
        raise last_timeout

    async def _write_with_retry(self, *, plan: WriteExecutionPlan, ctx: RequestContext):
        delays = [0, 1, 3]
        last_timeout: ConnectorTimeoutError | None = None

        for delay in delays:
            if delay:
                await asyncio.sleep(delay)
            try:
                return await self._router.route_write(plan, ctx.tenant_id)
            except ConnectorTimeoutError as exc:
                last_timeout = exc
                continue
            except (MissingScopeFilter, QueryInjectionAttempt):
                raise
            except (ConnectorAuthError, ConnectorError):
                raise

        assert last_timeout is not None
        raise last_timeout

    def _validate_scope(self, scope: ScopeFilter) -> None:
        if not scope.tenant_id:
            raise MissingScopeFilter("tenant_id is required in every ExecutionPlan scope")
