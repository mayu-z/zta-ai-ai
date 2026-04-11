from __future__ import annotations

from pathlib import Path

import httpx


def _require_existing_file(path_value: str, setting_name: str) -> str:
    normalized = path_value.strip()
    if not normalized:
        raise RuntimeError(
            f"{setting_name} is required when SERVICE_MTLS_ENABLED=true in production"
        )

    candidate = Path(normalized)
    if not candidate.is_file():
        raise RuntimeError(
            f"{setting_name} must point to an existing file: {normalized}"
        )

    return normalized


def validate_service_mtls_configuration(
    *,
    enabled: bool,
    client_cert_path: str,
    client_key_path: str,
    ca_bundle_path: str,
) -> None:
    if not enabled:
        raise RuntimeError("SERVICE_MTLS_ENABLED must be true in production")

    _require_existing_file(client_cert_path, "SERVICE_MTLS_CLIENT_CERT_PATH")
    _require_existing_file(client_key_path, "SERVICE_MTLS_CLIENT_KEY_PATH")
    _require_existing_file(ca_bundle_path, "SERVICE_MTLS_CA_BUNDLE_PATH")


def build_mtls_httpx_client(
    *,
    client_cert_path: str,
    client_key_path: str,
    ca_bundle_path: str,
    timeout_seconds: float = 30.0,
) -> httpx.Client:
    cert = _require_existing_file(client_cert_path, "SERVICE_MTLS_CLIENT_CERT_PATH")
    key = _require_existing_file(client_key_path, "SERVICE_MTLS_CLIENT_KEY_PATH")
    ca = _require_existing_file(ca_bundle_path, "SERVICE_MTLS_CA_BUNDLE_PATH")

    return httpx.Client(
        cert=(cert, key),
        verify=ca,
        timeout=timeout_seconds,
    )
