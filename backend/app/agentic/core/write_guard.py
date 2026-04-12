from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from app.core.exceptions import AuthorizationError


def _parse_write_target(write_target: str | None) -> tuple[set[str], str | None]:
    if not write_target:
        return set(), None

    table_part, _, op_part = write_target.partition(":")
    table = table_part.strip().lower() if table_part else None
    if not op_part:
        return set(), table

    operations = {
        token.strip().upper()
        for token in op_part.split(",")
        if token.strip()
    }
    return operations, table


def write_guard(*, allowed_ops: list[str], target_table: str) -> Callable[..., Any]:
    """Ensure agent writes only to configured table and operations."""

    normalized_allowed = {item.strip().upper() for item in allowed_ops}
    normalized_target = target_table.strip().lower()

    def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
        @wraps(func)
        async def wrapper(self, *args: Any, **kwargs: Any) -> Any:
            action = kwargs.get("action")
            if action is None and args:
                action = args[0]

            write_target = getattr(action, "write_target", None)
            configured_ops, configured_table = _parse_write_target(write_target)

            if configured_table != normalized_target:
                raise AuthorizationError(
                    message=(
                        f"Write target '{configured_table}' does not match required table "
                        f"'{normalized_target}'"
                    ),
                    code="WRITE_GUARD_TABLE_MISMATCH",
                )

            if configured_ops and not configured_ops.issubset(normalized_allowed):
                raise AuthorizationError(
                    message=(
                        "Configured write operations are not allowed for this code path"
                    ),
                    code="WRITE_GUARD_OPERATION_MISMATCH",
                )

            return await func(self, *args, **kwargs)

        return wrapper

    return decorator
