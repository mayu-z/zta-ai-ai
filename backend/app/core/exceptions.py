from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ZTAError(Exception):
    message: str
    code: str
    status_code: int = 400


class AuthenticationError(ZTAError):
    def __init__(
        self, message: str = "Authentication failed", code: str = "AUTH_FAILED"
    ) -> None:
        super().__init__(message=message, code=code, status_code=401)


class AuthorizationError(ZTAError):
    def __init__(
        self, message: str = "Access denied", code: str = "ACCESS_DENIED"
    ) -> None:
        super().__init__(message=message, code=code, status_code=403)


class ValidationError(ZTAError):
    def __init__(
        self, message: str = "Invalid request", code: str = "INVALID_REQUEST"
    ) -> None:
        super().__init__(message=message, code=code, status_code=422)


class UnsafeOutputError(ZTAError):
    def __init__(
        self,
        message: str = "Unsafe model output detected",
        code: str = "UNSAFE_MODEL_OUTPUT",
    ) -> None:
        super().__init__(message=message, code=code, status_code=500)


class RateLimitError(ZTAError):
    def __init__(
        self, message: str = "Rate limit exceeded", code: str = "RATE_LIMIT_EXCEEDED"
    ) -> None:
        super().__init__(message=message, code=code, status_code=429)
