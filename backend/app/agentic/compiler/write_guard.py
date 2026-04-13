from __future__ import annotations

from dataclasses import dataclass

from app.core.exceptions import AuthorizationError


@dataclass(frozen=True)
class ParsedWriteTarget:
    entity: str
    operation: str


class WriteGuard:
    """Validates write targets and action-level write authorization."""

    def __init__(self, allowed_operations: set[str] | None = None) -> None:
        self._allowed_operations = allowed_operations or {
            "INSERT",
            "UPDATE",
            "DELETE",
            "create_event",
            "send_email",
            "create_link",
        }

    def validate(self, *, action_id: str, write_target: str | None) -> ParsedWriteTarget:
        if not action_id:
            raise AuthorizationError(
                message="Action id is required for write validation",
                code="WRITE_GUARD_ACTION_MISSING",
            )
        if not write_target:
            raise AuthorizationError(
                message="Write target is missing for write action",
                code="WRITE_GUARD_TARGET_MISSING",
            )

        if "," in write_target:
            raise AuthorizationError(
                message="Multiple write targets are not allowed for a single action execution",
                code="WRITE_GUARD_MULTI_TARGET_DENIED",
            )

        target = write_target.strip()
        entity, sep, operation = target.partition(":")
        if not sep:
            raise AuthorizationError(
                message="Write target must be formatted as entity:OPERATION",
                code="WRITE_GUARD_TARGET_INVALID",
            )

        entity = entity.strip()
        operation = operation.strip()
        if not entity or not operation:
            raise AuthorizationError(
                message="Write target entity and operation are required",
                code="WRITE_GUARD_TARGET_INVALID",
            )

        normalized_op = operation if operation.islower() else operation.upper()
        if normalized_op not in self._allowed_operations:
            raise AuthorizationError(
                message=f"Write operation '{operation}' is not allowed",
                code="WRITE_GUARD_OPERATION_MISMATCH",
            )

        return ParsedWriteTarget(entity=entity, operation=normalized_op)
