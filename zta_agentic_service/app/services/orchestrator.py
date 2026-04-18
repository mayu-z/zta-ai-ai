from __future__ import annotations

import inspect
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from app.actions import ACTION_REGISTRY, BaseAction
from app.db.enums import ActionExecutionStatus
from app.db.models import ActionAuditLog, ActionExecution, ActionRegistry
from app.db.enums import ExecutionState
from app.db.session import SessionLocal
from app.integrations.ticketing import TicketingClient, get_ticketing_client
from app.schemas.execution import ExecutionResult
from app.services.context_manager import ContextManager, ExecutionContextSnapshot
from app.services.state_machine import ExecutionStateMachine
from app.services.step_executor import StepExecutionError, StepExecutor

logger = logging.getLogger(__name__)


class ExecutionOrchestrator:
    def __init__(
        self,
        state_machine: ExecutionStateMachine,
        step_executor: StepExecutor,
        context_manager: ContextManager,
        max_chain_depth: int = 3,
        redis_client: Any | None = None,
        ticketing_client: TicketingClient | None = None,
    ) -> None:
        self.state_machine = state_machine
        self.step_executor = step_executor
        self.context_manager = context_manager
        self.max_chain_depth = max_chain_depth
        self.redis = redis_client
        self.ticketing = ticketing_client or get_ticketing_client()

    def execute(
        self,
        agent_config: dict[str, Any],
        tenant_id: str,
        user_context: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> ExecutionResult:
        execution_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        logger.info(
            "orchestrator.execute_start",
            extra={
                "execution_id": execution_id,
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "agent_key": agent_config.get("agent_key") or agent_config.get("template_id"),
                "input_payload": input_payload,
                "resolver_invoked_here": False,
            },
        )

        chain_depth = int(input_payload.get("chain_depth", 0))
        if chain_depth > self.max_chain_depth:
            logger.info(
                "orchestrator.branch_chain_depth_limit",
                extra={
                    "execution_id": execution_id,
                    "chain_depth": chain_depth,
                    "max_chain_depth": self.max_chain_depth,
                },
            )
            return ExecutionResult(
                execution_id=execution_id,
                status="failed",
                state=ExecutionState.FAILED.value,
                output_summary="Chain depth limit exceeded",
            )

        snapshot = ExecutionContextSnapshot(
            execution_id=execution_id,
            tenant_id=tenant_id,
            user_id=user_context["user_id"],
            persona=user_context["persona"],
            definition_version_id=agent_config.get("definition_version_id") or "unversioned",
            config_version_id=agent_config.get("config_version_id") or "unversioned",
            trace_id=trace_id,
            chain_depth=chain_depth,
            chain_path=list(input_payload.get("chain_path", [])),
            token_map_ref=input_payload.get("token_map_ref"),
        )
        self.context_manager.save_snapshot(snapshot)

        current_state = ExecutionState.INIT
        logger.info(
            "orchestrator.state_entry",
            extra={"execution_id": execution_id, "state": current_state.value},
        )
        self.state_machine.transition(current_state, ExecutionState.VALIDATED, reason="preflight_passed")
        current_state = ExecutionState.VALIDATED
        logger.info(
            "orchestrator.state_transition",
            extra={"execution_id": execution_id, "state": current_state.value, "reason": "preflight_passed"},
        )

        if agent_config.get("requires_confirmation") and not input_payload.get("confirmed", False):
            self.state_machine.transition(
                current_state,
                ExecutionState.WAITING_CONFIRMATION,
                reason="confirmation_required",
            )
            logger.info(
                "orchestrator.branch_waiting_confirmation",
                extra={"execution_id": execution_id, "reason": "agent_requires_confirmation"},
            )
            return ExecutionResult(
                execution_id=execution_id,
                status="pending_confirmation",
                state=ExecutionState.WAITING_CONFIRMATION.value,
                requires_confirmation=True,
                next_actions=["confirm", "cancel"],
                output_summary=agent_config.get("confirmation_prompt") or "Confirmation required",
            )

        self.state_machine.transition(current_state, ExecutionState.RUNNING, reason="execution_started")
        current_state = ExecutionState.RUNNING
        logger.info(
            "orchestrator.state_transition",
            extra={"execution_id": execution_id, "state": current_state.value, "reason": "execution_started"},
        )

        steps = list(agent_config.get("action_steps", []))
        step_results: list[dict[str, Any]] = []
        logger.info(
            "orchestrator.steps_loaded",
            extra={"execution_id": execution_id, "step_count": len(steps)},
        )

        try:
            for idx, step in enumerate(steps):
                result = self.step_executor.execute_step(
                    step=step,
                    context={
                        "tenant_id": tenant_id,
                        "user_context": user_context,
                        "variables": input_payload,
                        "confirmed": input_payload.get("confirmed", False),
                    },
                )
                self.context_manager.update_step_pointer(execution_id, idx)
                step_results.append(result.output)
                logger.info(
                    "orchestrator.step_result",
                    extra={
                        "execution_id": execution_id,
                        "step_index": idx,
                        "step_id": result.step_id,
                        "step_status": result.status,
                        "output": result.output,
                    },
                )

                if result.status == "waiting_confirmation":
                    self.state_machine.transition(
                        current_state,
                        ExecutionState.WAITING_CONFIRMATION,
                        reason=f"step_{result.step_id}_requires_confirmation",
                    )
                    return ExecutionResult(
                        execution_id=execution_id,
                        status="pending_confirmation",
                        state=ExecutionState.WAITING_CONFIRMATION.value,
                        requires_confirmation=True,
                        next_actions=["confirm", "cancel"],
                    )

            self.state_machine.transition(current_state, ExecutionState.COMPLETED, reason="all_steps_succeeded")
            logger.info(
                "orchestrator.state_transition",
                extra={"execution_id": execution_id, "state": ExecutionState.COMPLETED.value, "reason": "all_steps_succeeded"},
            )
            return ExecutionResult(
                execution_id=execution_id,
                status="completed",
                state=ExecutionState.COMPLETED.value,
                output_summary="Execution completed",
            )

        except StepExecutionError as exc:
            self.state_machine.transition(current_state, ExecutionState.FAILED, reason=exc.error_class)
            logger.info(
                "orchestrator.state_transition",
                extra={
                    "execution_id": execution_id,
                    "state": ExecutionState.FAILED.value,
                    "reason": exc.error_class,
                    "error": str(exc),
                },
            )
            return ExecutionResult(
                execution_id=execution_id,
                status="failed",
                state=ExecutionState.FAILED.value,
                output_summary=str(exc),
            )

    def execute_action_workflow(
        self,
        *,
        action_names: list[str],
        triggered_by: str,
        payload: dict[str, Any],
        mode: str = "sequential",
        dry_run: bool = False,
        approved: bool = False,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        workflow_mode = mode.lower().strip()
        if workflow_mode not in {"sequential", "parallel"}:
            raise ValueError("workflow mode must be 'sequential' or 'parallel'")

        db = SessionLocal()
        try:
            if execution_id:
                execution = db.get(ActionExecution, execution_id)
                if execution is None:
                    raise KeyError(f"Unknown action execution: {execution_id}")
                context_payload = dict(execution.payload or {})
                action_names = list(context_payload.get("action_names", action_names))
                triggered_by = context_payload.get("triggered_by", triggered_by)
                payload = dict(context_payload.get("action_payload", payload))
                dry_run = bool(context_payload.get("dry_run", dry_run))
                workflow_mode = context_payload.get("mode", workflow_mode)
            else:
                execution = ActionExecution(
                    action_name="+".join(action_names),
                    triggered_by=triggered_by,
                    status=ActionExecutionStatus.PENDING,
                    dry_run=dry_run,
                    payload={
                        "action_names": action_names,
                        "triggered_by": triggered_by,
                        "action_payload": payload,
                        "mode": workflow_mode,
                        "dry_run": dry_run,
                    },
                    result={},
                )
                db.add(execution)
                db.commit()
                db.refresh(execution)

            definitions = db.scalars(
                select(ActionRegistry).where(ActionRegistry.name.in_(action_names), ActionRegistry.is_active.is_(True))
            ).all()
            definition_by_name = {row.name: row for row in definitions}
            missing = [name for name in action_names if name not in definition_by_name]
            if missing:
                raise KeyError(f"Unknown or inactive actions: {', '.join(missing)}")

            if dry_run:
                step_results = []
                for action_name in action_names:
                    action = self._build_action(action_name=action_name, db=db, actor=triggered_by)
                    preview = action.dry_run({**payload, "execution_id": str(execution.id)})
                    step_results.append({"action": action_name, "preview": action.to_dict(preview)})
                    action.audit_log(
                        execution_id=str(execution.id),
                        step=f"dry_run_{action_name}",
                        outcome="preview",
                        payload_in=payload,
                        payload_out=action.to_dict(preview),
                        actor=triggered_by,
                    )

                execution.status = ActionExecutionStatus.COMPLETED
                execution.result = {"preview_only": True, "mode": workflow_mode, "steps": step_results}
                execution.completed_at = datetime.now(UTC)
                db.add(execution)
                db.commit()
                return {
                    "execution_id": str(execution.id),
                    "status": execution.status.value,
                    "preview_only": True,
                    "result": execution.result,
                }

            requiring_approval = [definition_by_name[name] for name in action_names if definition_by_name[name].requires_approval]
            if requiring_approval and not approved:
                sla_hours = max(item.approval_sla_hours for item in requiring_approval)
                execution.status = ActionExecutionStatus.AWAITING_APPROVAL
                execution.result = {
                    "awaiting_approval_for": [item.name for item in requiring_approval],
                    "approval_sla_hours": sla_hours,
                    "next_action": "approve_or_reject",
                }
                db.add(execution)
                db.commit()
                self._set_approval_sla(execution_id=str(execution.id), sla_hours=sla_hours)
                return {
                    "execution_id": str(execution.id),
                    "status": execution.status.value,
                    "preview_only": dry_run,
                    "result": execution.result,
                }

            execution.status = ActionExecutionStatus.RUNNING
            db.add(execution)
            db.commit()

            if workflow_mode == "parallel":
                step_results, failures, completed_steps = self._run_parallel_actions(
                    execution=execution,
                    action_names=action_names,
                    payload=payload,
                    triggered_by=triggered_by,
                )
            else:
                step_results, failures, completed_steps = self._run_sequential_actions(
                    db=db,
                    execution=execution,
                    action_names=action_names,
                    payload=payload,
                    triggered_by=triggered_by,
                )

            if failures:
                rollback_results = self._rollback_completed_actions(
                    db=db,
                    execution_id=str(execution.id),
                    action_names=completed_steps,
                    actor=triggered_by,
                )
                execution.status = ActionExecutionStatus.ROLLED_BACK if rollback_results else ActionExecutionStatus.FAILED
                execution.result = {
                    "mode": workflow_mode,
                    "steps": step_results,
                    "completed_steps": completed_steps,
                    "failures": failures,
                    "rollback": rollback_results,
                }
                execution.completed_at = datetime.now(UTC)
                db.add(execution)
                db.commit()
                return {
                    "execution_id": str(execution.id),
                    "status": execution.status.value,
                    "preview_only": False,
                    "result": execution.result,
                }

            execution.status = ActionExecutionStatus.COMPLETED
            execution.result = {"mode": workflow_mode, "steps": step_results, "completed_steps": completed_steps}
            execution.completed_at = datetime.now(UTC)
            db.add(execution)
            db.commit()
            return {
                "execution_id": str(execution.id),
                "status": execution.status.value,
                "preview_only": False,
                "result": execution.result,
            }
        finally:
            db.close()

    def approve_action_execution(self, execution_id: str, actor_user_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.get(ActionExecution, execution_id)
            if row is None:
                raise KeyError(f"Unknown action execution: {execution_id}")
            if row.status != ActionExecutionStatus.AWAITING_APPROVAL:
                raise ValueError("Execution is not awaiting approval")

            row.status = ActionExecutionStatus.APPROVED
            row.result = {**(row.result or {}), "approved_by": actor_user_id, "approved_at": datetime.now(UTC).isoformat()}
            db.add(row)
            db.commit()
            self._clear_approval_sla(execution_id)

            resumed = self.execute_action_workflow(
                action_names=list((row.payload or {}).get("action_names", [])),
                triggered_by=str((row.payload or {}).get("triggered_by", actor_user_id)),
                payload=dict((row.payload or {}).get("action_payload", {})),
                mode=str((row.payload or {}).get("mode", "sequential")),
                dry_run=bool((row.payload or {}).get("dry_run", False)),
                approved=True,
                execution_id=execution_id,
            )
            return resumed
        finally:
            db.close()

    def reject_action_execution(self, execution_id: str, actor_user_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.get(ActionExecution, execution_id)
            if row is None:
                raise KeyError(f"Unknown action execution: {execution_id}")
            if row.status != ActionExecutionStatus.AWAITING_APPROVAL:
                raise ValueError("Execution is not awaiting approval")

            completed_steps = list((row.result or {}).get("completed_steps", []))
            rollback_results: list[dict[str, Any]] = []
            if completed_steps:
                rollback_results = self._rollback_completed_actions(
                    db=db,
                    execution_id=execution_id,
                    action_names=completed_steps,
                    actor=actor_user_id,
                )

            row.status = ActionExecutionStatus.ROLLED_BACK if rollback_results else ActionExecutionStatus.REJECTED
            row.completed_at = datetime.now(UTC)
            row.result = {
                **(row.result or {}),
                "rejected_by": actor_user_id,
                "rejected_at": datetime.now(UTC).isoformat(),
                "rollback": rollback_results,
            }
            db.add(row)
            db.commit()
            self._clear_approval_sla(execution_id)
            return {
                "execution_id": execution_id,
                "status": row.status.value,
                "result": row.result,
            }
        finally:
            db.close()

    def get_action_status(self, execution_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            row = db.get(ActionExecution, execution_id)
            if row is None:
                raise KeyError(f"Unknown action execution: {execution_id}")
            return {
                "execution_id": str(row.id),
                "action_name": row.action_name,
                "status": row.status.value,
                "dry_run": row.dry_run,
                "result": row.result,
                "created_at": row.created_at.isoformat(),
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
            }
        finally:
            db.close()

    def get_action_audit(self, execution_id: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            items = db.scalars(
                select(ActionAuditLog)
                .where(ActionAuditLog.execution_id == execution_id)
                .order_by(ActionAuditLog.timestamp.asc())
            ).all()
            return {
                "execution_id": execution_id,
                "items": [
                    {
                        "id": str(item.id),
                        "step_name": item.step_name,
                        "actor": item.actor,
                        "outcome": item.outcome,
                        "payload_hash": item.payload_hash,
                        "timestamp": item.timestamp.isoformat(),
                    }
                    for item in items
                ],
            }
        finally:
            db.close()

    def _run_sequential_actions(
        self,
        *,
        db: Any,
        execution: ActionExecution,
        action_names: list[str],
        payload: dict[str, Any],
        triggered_by: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        steps: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        completed: list[str] = []
        for action_name in action_names:
            action = self._build_action(action_name=action_name, db=db, actor=triggered_by)
            try:
                result = action.execute({**payload, "execution_id": str(execution.id)})
                steps.append({"action": action_name, "result": action.to_dict(result)})
                completed.append(action_name)
            except Exception as exc:
                failures.append({"action": action_name, "error": str(exc)})
                break
        return steps, failures, completed

    def _run_parallel_actions(
        self,
        *,
        execution: ActionExecution,
        action_names: list[str],
        payload: dict[str, Any],
        triggered_by: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        steps: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        completed: list[str] = []

        child_execution_ids: dict[str, str] = {}
        setup_db = SessionLocal()
        try:
            for action_name in action_names:
                child = ActionExecution(
                    action_name=action_name,
                    triggered_by=triggered_by,
                    status=ActionExecutionStatus.RUNNING,
                    dry_run=False,
                    payload={**payload, "parent_execution_id": str(execution.id)},
                    result={},
                )
                setup_db.add(child)
                setup_db.flush()
                child_execution_ids[action_name] = str(child.id)
            setup_db.commit()
        finally:
            setup_db.close()

        def worker(action_name: str, child_execution_id: str) -> dict[str, Any]:
            db = SessionLocal()
            try:
                action = self._build_action(action_name=action_name, db=db, actor=triggered_by)
                result = action.execute({**payload, "execution_id": child_execution_id})
                child_row = db.get(ActionExecution, child_execution_id)
                if child_row is not None:
                    child_row.status = ActionExecutionStatus.COMPLETED
                    child_row.completed_at = datetime.now(UTC)
                    db.add(child_row)
                    db.commit()
                return {"action": action_name, "result": action.to_dict(result), "child_execution_id": child_execution_id}
            finally:
                db.close()

        with ThreadPoolExecutor(max_workers=max(1, len(action_names))) as pool:
            future_map = {
                pool.submit(worker, name, child_execution_ids[name]): name for name in action_names
            }
            for future in as_completed(future_map):
                action_name = future_map[future]
                try:
                    data = future.result()
                    steps.append(data)
                    completed.append(action_name)
                except Exception as exc:
                    failures.append({"action": action_name, "error": str(exc)})

        return steps, failures, completed

    def _rollback_completed_actions(
        self,
        *,
        db: Any,
        execution_id: str,
        action_names: list[str],
        actor: str,
    ) -> list[dict[str, Any]]:
        rollback_results: list[dict[str, Any]] = []
        for action_name in reversed(action_names):
            action = self._build_action(action_name=action_name, db=db, actor=actor)
            try:
                result = action.rollback(execution_id)
                rollback_results.append({"action": action_name, "result": action.to_dict(result)})
            except Exception as exc:
                rollback_results.append({"action": action_name, "error": str(exc)})
        return rollback_results

    def _build_action(self, *, action_name: str, db: Any, actor: str) -> BaseAction:
        action_cls = ACTION_REGISTRY.get(action_name)
        if action_cls is None:
            raise KeyError(f"Unknown action: {action_name}")

        params = inspect.signature(action_cls.__init__).parameters
        kwargs: dict[str, Any] = {"db": db, "actor": actor}
        if "ticketing" in params:
            kwargs["ticketing"] = self.ticketing
        return action_cls(**kwargs)

    def _set_approval_sla(self, execution_id: str, sla_hours: int) -> None:
        if self.redis is None:
            return
        ttl_seconds = max(1, int(sla_hours) * 3600)
        key = f"action:sla:{execution_id}"
        self.redis.set(key, "awaiting_approval", ex=ttl_seconds)
        try:
            from app.workers.tasks import escalation_timer_task

            escalation_timer_task.apply_async(args=[execution_id], countdown=ttl_seconds)
        except Exception as exc:  # pragma: no cover - async queue should not block primary path
            logger.warning("orchestrator.sla_task_schedule_failed", extra={"execution_id": execution_id, "error": str(exc)})

    def _clear_approval_sla(self, execution_id: str) -> None:
        if self.redis is None:
            return
        self.redis.delete(f"action:sla:{execution_id}")
