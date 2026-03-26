from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    import jwt
except Exception:  # noqa: BLE001
    jwt = None  # type: ignore[assignment]

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _encode_fallback(payload: dict[str, Any], secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    header_part = _b64url_encode(json.dumps(header, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    payload_part = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=True).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header_part}.{payload_part}.{_b64url_encode(signature)}"


def _decode_fallback(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise AuthenticationError(message="Invalid token format", code="INVALID_TOKEN")

    header_raw, payload_raw, sig_raw = parts

    try:
        header = json.loads(_b64url_decode(header_raw).decode("utf-8"))
        payload = json.loads(_b64url_decode(payload_raw).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise AuthenticationError(message="Token decode failed", code="INVALID_TOKEN") from exc

    if header.get("alg") != "HS256":
        raise AuthenticationError(message="Token algorithm not allowed", code="TOKEN_ALG_REJECTED")

    signing_input = f"{header_raw}.{payload_raw}".encode("ascii")
    expected_sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()

    if not hmac.compare_digest(expected_sig, _b64url_decode(sig_raw)):
        raise AuthenticationError(message="Invalid token signature", code="INVALID_TOKEN")

    now_ts = int(utc_now().timestamp())
    exp = int(payload.get("exp", 0))
    iat = int(payload.get("iat", 0))
    if exp <= now_ts or iat <= 0:
        raise AuthenticationError(message="Invalid or expired token", code="INVALID_TOKEN")

    return payload


def create_access_token(payload: dict[str, Any], expires_minutes: int | None = None) -> str:
    settings = get_settings()
    token_payload = dict(payload)
    exp_minutes = expires_minutes if expires_minutes is not None else settings.jwt_exp_minutes
    issued_at = utc_now()
    expires_at = issued_at + timedelta(minutes=exp_minutes)
    token_payload.update({"iat": int(issued_at.timestamp()), "exp": int(expires_at.timestamp())})

    if jwt is not None:
        return jwt.encode(token_payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return _encode_fallback(token_payload, settings.jwt_secret_key)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()

    if jwt is not None:
        try:
            decoded = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
                options={"require": ["exp", "iat"]},
            )
        except Exception as exc:  # noqa: BLE001
            raise AuthenticationError(message="Invalid or expired token", code="INVALID_TOKEN") from exc

        return decoded

    return _decode_fallback(token, settings.jwt_secret_key)


def normalize_text(value: str) -> str:
    return " ".join(value.strip().lower().split())


def stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def build_intent_hash(normalized_intent: dict[str, Any], tenant_id: str) -> str:
    canonical = stable_json({"tenant_id": tenant_id, "intent": normalized_intent})
    return sha256_hex(canonical)


def contains_raw_number(value: str) -> bool:
    import re

    text = re.sub(r"\[SLOT_\d+\]", "", value)
    return bool(re.search(r"\b\d+(?:\.\d+)?\b", text))
