from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agentic.db_models import AgenticWorkflowStateModel
from app.agentic.models.agent_context import RequestContext
from app.agentic.models.audit_event import AuditEvent
from app.agentic.models.workflow_state import WorkflowState, WorkflowStatus, WorkflowStep
from app.db.session import SessionLocal


class InvalidTransition(Exception):
    pass


class WorkflowEngine:
    ALLOWED_TRANSITIONS = {
        "leave_approval": {
            "DRAFT": ["SUBMITTED", "CANCELLED"],
            "SUBMITTED": ["PENDING_APPROVER", "CANCELLED"],
            "PENDING_APPROVER": ["APPROVED", "REJECTED", "PENDING_MORE_INFO"],
            "PENDING_MORE_INFO": ["PENDING_APPROVER", "CANCELLED"],
            "APPROVED": ["NOTIFIED"],
            "REJECTED": ["NOTIFIED"],
            "NOTIFIED": [],
        },
        "refund_processing": {
            "SUBMITTED": ["PENDING_FINANCE", "CANCELLED"],
            "PENDING_FINANCE": ["APPROVED", "REJECTED"],
            "APPROVED": ["PROCESSING", "FAILED"],
            "PROCESSING": ["COMPLETED", "FAILED"],
            "COMPLETED": ["NOTIFIED"],
            "FAILED": ["NOTIFIED"],
            "NOTIFIED": [],
        },
    }

    def __init__(self, audit_logger) -> None:
        self._audit = audit_logger

    def _serialize_steps(self, steps: list[WorkflowStep]) -> list[dict]:
        payload: list[dict] = []
        for step in steps:
            row = asdict(step)
            if step.completed_at is not None:
                row["completed_at"] = step.completed_at.isoformat()
            payload.append(row)
        return payload

    def _deserialize_steps(self, rows: list[dict]) -> list[WorkflowStep]:
        steps: list[WorkflowStep] = []
        for row in rows:
            completed_at = row.get("completed_at")
            steps.append(
                WorkflowStep(
                    step_id=row["step_id"],
                    step_name=row["step_name"],
                    status=row["status"],
                    actor_alias=row.get("actor_alias"),
                    completed_at=(datetime.fromisoformat(completed_at) if completed_at else None),
                    metadata=row.get("metadata", {}),
                )
            )
        return steps

    async def create(
        self,
        workflow_type: str,
        initial_steps: list[WorkflowStep],
        ctx: RequestContext,
    ) -> WorkflowState:
        workflow_id = f"wf_{uuid4().hex}"
        now = datetime.utcnow()
        current_step = initial_steps[0].step_name if initial_steps else "DRAFT"
        state = WorkflowState(
            workflow_id=workflow_id,
            workflow_type=workflow_type,
            tenant_id=ctx.tenant_id,
            initiator_alias=ctx.user_alias,
            current_step=current_step,
            status=WorkflowStatus.ACTIVE,
            steps=initial_steps,
            created_at=now,
            updated_at=now,
        )

        db = SessionLocal()
        try:
            db.add(
                AgenticWorkflowStateModel(
                    workflow_id=workflow_id,
                    workflow_type=workflow_type,
                    tenant_id=str(ctx.tenant_id),
                    initiator_alias=ctx.user_alias,
                    current_step=current_step,
                    status=WorkflowStatus.ACTIVE.value,
                    steps=self._serialize_steps(initial_steps),
                    workflow_metadata={},
                    created_at=now,
                    updated_at=now,
                )
            )
            db.commit()
        finally:
            db.close()

        await self._audit.write(
            AuditEvent(
                event_type="WORKFLOW_CREATED",
                action_id=workflow_type,
                user_alias=ctx.user_alias,
                tenant_id=ctx.tenant_id,
                status="ACTIVE",
                metadata={"workflow_id": workflow_id},
            )
        )

        return state

    async def transition(
        self,
        workflow_id: str,
        new_state: str,
        actor_alias: str,
        ctx: RequestContext,
        metadata: dict = {},
    ) -> WorkflowState:
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticWorkflowStateModel)
                .where(AgenticWorkflowStateModel.workflow_id == workflow_id)
                .where(AgenticWorkflowStateModel.tenant_id == str(ctx.tenant_id))
            )
            if row is None:
                raise InvalidTransition("workflow not found")

            allowed = self.ALLOWED_TRANSITIONS.get(row.workflow_type, {}).get(row.current_step, [])
            if new_state not in allowed:
                raise InvalidTransition(
                    f"invalid transition: {row.current_step} -> {new_state}"
                )

            steps = self._deserialize_steps(row.steps)
            updated = False
            for step in steps:
                if step.step_name == row.current_step and step.status == "PENDING":
                    step.status = "COMPLETED"
                    step.actor_alias = actor_alias
                    step.completed_at = datetime.utcnow()
                    updated = True
                    break

            if not updated:
                steps.append(
                    WorkflowStep(
                        step_id=f"step_{len(steps)+1}",
                        step_name=row.current_step,
                        status="COMPLETED",
                        actor_alias=actor_alias,
                        completed_at=datetime.utcnow(),
                    )
                )

            steps.append(
                WorkflowStep(
                    step_id=f"step_{len(steps)+1}",
                    step_name=new_state,
                    status="PENDING",
                    metadata=metadata,
                )
            )

            row.current_step = new_state
            if new_state in {"NOTIFIED", "COMPLETED"}:
                row.status = WorkflowStatus.COMPLETED.value
            elif new_state in {"REJECTED", "FAILED"}:
                row.status = WorkflowStatus.FAILED.value
            elif new_state == "CANCELLED":
                row.status = WorkflowStatus.CANCELLED.value
            else:
                row.status = WorkflowStatus.ACTIVE.value
            row.steps = self._serialize_steps(steps)
            row.workflow_metadata = dict(row.workflow_metadata or {}) | dict(metadata or {})
            row.updated_at = datetime.utcnow()
            db.commit()

            state = WorkflowState(
                workflow_id=row.workflow_id,
                workflow_type=row.workflow_type,
                tenant_id=UUID(row.tenant_id),
                initiator_alias=row.initiator_alias,
                current_step=row.current_step,
                status=WorkflowStatus(row.status),
                steps=steps,
                created_at=row.created_at,
                updated_at=row.updated_at,
                metadata=dict(row.workflow_metadata or {}),
            )
        finally:
            db.close()

        await self._audit.write(
            AuditEvent(
                event_type="WORKFLOW_TRANSITION",
                action_id=state.workflow_type,
                user_alias=actor_alias,
                tenant_id=ctx.tenant_id,
                status=state.current_step,
                metadata={"workflow_id": workflow_id, "new_state": new_state},
            )
        )
        return state

    async def get_state(self, workflow_id: str, tenant_id: UUID) -> WorkflowState | None:
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AgenticWorkflowStateModel)
                .where(AgenticWorkflowStateModel.workflow_id == workflow_id)
                .where(AgenticWorkflowStateModel.tenant_id == str(tenant_id))
            )
            if row is None:
                return None
            return WorkflowState(
                workflow_id=row.workflow_id,
                workflow_type=row.workflow_type,
                tenant_id=UUID(row.tenant_id),
                initiator_alias=row.initiator_alias,
                current_step=row.current_step,
                status=WorkflowStatus(row.status),
                steps=self._deserialize_steps(row.steps),
                created_at=row.created_at,
                updated_at=row.updated_at,
                metadata=dict(row.workflow_metadata or {}),
            )
        finally:
            db.close()

    async def cancel(
        self,
        workflow_id: str,
        actor_alias: str,
        reason: str,
        ctx: RequestContext,
    ) -> WorkflowState:
        return await self.transition(
            workflow_id=workflow_id,
            new_state="CANCELLED",
            actor_alias=actor_alias,
            ctx=ctx,
            metadata={"reason": reason},
        )
