from dataclasses import dataclass
import logging

from app.db.enums import ExecutionState

logger = logging.getLogger(__name__)


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
        logger.info(
            "state_machine.transition_attempt",
            extra={
                "from_state": current_state.value,
                "to_state": next_state.value,
                "reason": reason,
                "actor_user_id": actor_user_id,
            },
        )
        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        if next_state not in allowed:
            logger.info(
                "state_machine.transition_rejected",
                extra={
                    "from_state": current_state.value,
                    "to_state": next_state.value,
                    "reason": reason,
                    "allowed_transitions": [state.value for state in allowed],
                },
            )
            raise InvalidStateTransitionError(
                f"Invalid transition {current_state.value} -> {next_state.value}"
            )
        logger.info(
            "state_machine.transition_applied",
            extra={"from_state": current_state.value, "to_state": next_state.value, "reason": reason},
        )
        return TransitionRecord(
            from_state=current_state,
            to_state=next_state,
            reason=reason,
            actor_user_id=actor_user_id,
        )
