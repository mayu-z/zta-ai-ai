from __future__ import annotations

import uuid
from typing import Any

from app.db.enums import ExecutionState
from app.schemas.execution import ExecutionResult
from app.services.context_manager import ContextManager, ExecutionContextSnapshot
from app.services.state_machine import ExecutionStateMachine
from app.services.step_executor import StepExecutionError, StepExecutor


class ExecutionOrchestrator:
    def __init__(
        self,
        state_machine: ExecutionStateMachine,
        step_executor: StepExecutor,
        context_manager: ContextManager,
        max_chain_depth: int = 3,
    ) -> None:
        self.state_machine = state_machine
        self.step_executor = step_executor
        self.context_manager = context_manager
        self.max_chain_depth = max_chain_depth

    def execute(
        self,
        agent_config: dict[str, Any],
        tenant_id: str,
        user_context: dict[str, Any],
        input_payload: dict[str, Any],
    ) -> ExecutionResult:
        execution_id = str(uuid.uuid4())
        trace_id = str(uuid.uuid4())

        chain_depth = int(input_payload.get("chain_depth", 0))
        if chain_depth > self.max_chain_depth:
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
        self.state_machine.transition(current_state, ExecutionState.VALIDATED, reason="preflight_passed")
        current_state = ExecutionState.VALIDATED

        if agent_config.get("requires_confirmation") and not input_payload.get("confirmed", False):
            self.state_machine.transition(
                current_state,
                ExecutionState.WAITING_CONFIRMATION,
                reason="confirmation_required",
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

        steps = list(agent_config.get("action_steps", []))
        step_results: list[dict[str, Any]] = []

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
            return ExecutionResult(
                execution_id=execution_id,
                status="completed",
                state=ExecutionState.COMPLETED.value,
                output_summary="Execution completed",
            )

        except StepExecutionError as exc:
            self.state_machine.transition(current_state, ExecutionState.FAILED, reason=exc.error_class)
            return ExecutionResult(
                execution_id=execution_id,
                status="failed",
                state=ExecutionState.FAILED.value,
                output_summary=str(exc),
            )
