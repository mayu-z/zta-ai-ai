from dataclasses import dataclass

from app.db.enums import ExecutionState


class InvalidStateTransitionError(ValueError):
    pass


ALLOWED_TRANSITIONS: dict[ExecutionState, set[ExecutionState]] = {
    ExecutionState.INIT: {ExecutionState.VALIDATED, ExecutionState.FAILED},
    ExecutionState.VALIDATED: {
        ExecutionState.RUNNING,
        ExecutionState.WAITING_CONFIRMATION,
        ExecutionState.WAITING_APPROVAL,
        ExecutionState.FAILED,
    },
    ExecutionState.RUNNING: {ExecutionState.COMPLETED, ExecutionState.FAILED},
    ExecutionState.WAITING_CONFIRMATION: {ExecutionState.RESUMED, ExecutionState.FAILED},
    ExecutionState.WAITING_APPROVAL: {ExecutionState.RESUMED, ExecutionState.FAILED},
    ExecutionState.RESUMED: {ExecutionState.RUNNING, ExecutionState.FAILED},
    ExecutionState.COMPLETED: set(),
    ExecutionState.FAILED: set(),
}


@dataclass
class TransitionRecord:
    from_state: ExecutionState
    to_state: ExecutionState
    reason: str
    actor_user_id: str | None = None


class ExecutionStateMachine:
    def transition(
        self,
        current_state: ExecutionState,
        next_state: ExecutionState,
        reason: str,
        actor_user_id: str | None = None,
    ) -> TransitionRecord:
        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        if next_state not in allowed:
            raise InvalidStateTransitionError(
                f"Invalid transition {current_state.value} -> {next_state.value}"
            )
        return TransitionRecord(
            from_state=current_state,
            to_state=next_state,
            reason=reason,
            actor_user_id=actor_user_id,
        )
