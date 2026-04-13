from __future__ import annotations

import pytest

from app.agentic.compiler.write_guard import WriteGuard
from app.core.exceptions import AuthorizationError


def test_write_guard_validates_target() -> None:
    guard = WriteGuard()

    parsed = guard.validate(action_id="leave_balance_apply_v1", write_target="leave_records:INSERT")

    assert parsed.entity == "leave_records"
    assert parsed.operation == "INSERT"


def test_write_guard_rejects_invalid_target() -> None:
    guard = WriteGuard()

    with pytest.raises(AuthorizationError):
        guard.validate(action_id="a1", write_target="leave_records")


def test_write_guard_rejects_unknown_operation() -> None:
    guard = WriteGuard()

    with pytest.raises(AuthorizationError):
        guard.validate(action_id="a1", write_target="leave_records:TRUNCATE")
