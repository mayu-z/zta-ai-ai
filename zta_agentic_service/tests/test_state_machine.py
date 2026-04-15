import pytest

from app.db.enums import ExecutionState
from app.services.state_machine import ExecutionStateMachine, InvalidStateTransitionError


@pytest.mark.parametrize(
    ("current", "next_state"),
    [
        (ExecutionState.INIT, ExecutionState.VALIDATED),
        (ExecutionState.VALIDATED, ExecutionState.RUNNING),
        (ExecutionState.WAITING_CONFIRMATION, ExecutionState.RESUMED),
        (ExecutionState.RESUMED, ExecutionState.RUNNING),
        (ExecutionState.RUNNING, ExecutionState.COMPLETED),
    ],
)
def test_valid_state_transitions(current: ExecutionState, next_state: ExecutionState) -> None:
    sm = ExecutionStateMachine()
    record = sm.transition(current, next_state, reason="test")
    assert record.from_state == current
    assert record.to_state == next_state


def test_invalid_state_transition() -> None:
    sm = ExecutionStateMachine()
    with pytest.raises(InvalidStateTransitionError):
        sm.transition(ExecutionState.INIT, ExecutionState.COMPLETED, reason="invalid")
