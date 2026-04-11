from __future__ import annotations

import base64
import hashlib
import hmac
import time

from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.main import app


def _totp_code(secret: str, period_seconds: int) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * (-len(normalized) % 8)
    secret_bytes = base64.b32decode(normalized + padding, casefold=True)

    counter = int(time.time() // period_seconds)
    payload = counter.to_bytes(8, "big")
    digest = hmac.new(secret_bytes, payload, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = (
        ((digest[offset] & 0x7F) << 24)
        | ((digest[offset + 1] & 0xFF) << 16)
        | ((digest[offset + 2] & 0xFF) << 8)
        | (digest[offset + 3] & 0xFF)
    )
    return f"{code_int % 1_000_000:06d}"


def test_mfa_totp_api_flow() -> None:
    settings = get_settings()

    with TestClient(app) as client:
        login_resp = client.post(
            "/auth/google",
            json={"google_token": "mock:executive@ipeds.local"},
        )
        assert login_resp.status_code == 200

        jwt_token = login_resp.json()["jwt"]
        headers = {"Authorization": f"Bearer {jwt_token}"}

        enroll_resp = client.post("/auth/mfa/totp/enroll", headers=headers)
        assert enroll_resp.status_code == 200
        enrolled = enroll_resp.json()
        assert enrolled["method"] == "totp"

        code = _totp_code(
            enrolled["secret"],
            period_seconds=settings.mfa_totp_period_seconds,
        )
        verify_resp = client.post(
            "/auth/mfa/totp/verify",
            headers=headers,
            json={"code": code},
        )
        assert verify_resp.status_code == 200

        verified_jwt = verify_resp.json()["jwt"]
        payload = decode_access_token(verified_jwt)
        assert payload["mfa_verified"] is True
