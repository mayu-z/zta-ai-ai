from __future__ import annotations

import pytest

from app.core.egress import enforce_egress_url_allowed


def test_enforce_egress_url_allowed_accepts_exact_host() -> None:
    enforce_egress_url_allowed(
        target_url="https://integrate.api.nvidia.com/v1",
        raw_allowlist="integrate.api.nvidia.com",
    )


def test_enforce_egress_url_allowed_accepts_wildcard_host() -> None:
    enforce_egress_url_allowed(
        target_url="https://api.example.com/v1",
        raw_allowlist="*.example.com",
    )


def test_enforce_egress_url_allowed_blocks_unlisted_host() -> None:
    with pytest.raises(RuntimeError):
        enforce_egress_url_allowed(
            target_url="https://api.evil.example/v1",
            raw_allowlist="integrate.api.nvidia.com,*.trusted.example",
        )
