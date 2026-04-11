from __future__ import annotations

from importlib import reload

import pytest

import app.main as main_module


def _create_mtls_artifacts(tmp_path) -> tuple[str, str, str]:
    cert = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    ca = tmp_path / "ca.crt"
    cert.write_text("dummy-cert", encoding="utf-8")
    key.write_text("dummy-key", encoding="utf-8")
    ca.write_text("dummy-ca", encoding="utf-8")
    return str(cert), str(key), str(ca)


@pytest.mark.parametrize(
    "env,auth_provider,mock_oauth,jwt_secret,oidc_issuer,oidc_audience,oidc_shared_secret,saml_metadata,saml_entity,egress_allowlist,slm_base_url,should_raise",
    [
        (
            "development",
            "mock_google",
            True,
            "short",
            "",
            "",
            "",
            "",
            "",
            "",
            "https://integrate.api.nvidia.com/v1",
            False,
        ),
        (
            "production",
            "mock_google",
            False,
            "x" * 64,
            "",
            "",
            "",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            True,
            "x" * 64,
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "change-me",
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 16,
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 64,
            "",
            "",
            "",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 64,
            "https://idp.example.com",
            "zta-backend",
            "",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 64,
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 64,
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://api.not-allowed.example/v1",
            True,
        ),
        (
            "production",
            "oidc",
            False,
            "x" * 64,
            "https://idp.example.com",
            "zta-backend",
            "oidc-test-secret",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            False,
        ),
        (
            "production",
            "saml",
            False,
            "x" * 64,
            "",
            "",
            "",
            "",
            "",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            True,
        ),
        (
            "production",
            "saml",
            False,
            "x" * 64,
            "",
            "",
            "",
            "https://idp.example.com/metadata",
            "zta-backend",
            "integrate.api.nvidia.com",
            "https://integrate.api.nvidia.com/v1",
            False,
        ),
    ],
)
def test_enforce_startup_security(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    env: str,
    auth_provider: str,
    mock_oauth: bool,
    jwt_secret: str,
    oidc_issuer: str,
    oidc_audience: str,
    oidc_shared_secret: str,
    saml_metadata: str,
    saml_entity: str,
    egress_allowlist: str,
    slm_base_url: str,
    should_raise: bool,
) -> None:
    # Reload main module so settings object can be monkeypatched deterministically.
    reload(main_module)
    cert_path, key_path, ca_path = _create_mtls_artifacts(tmp_path)

    monkeypatch.setattr(main_module.settings, "environment", env)
    monkeypatch.setattr(main_module.settings, "secrets_backend", "env")
    monkeypatch.setattr(main_module.settings, "auth_provider", auth_provider)
    monkeypatch.setattr(main_module.settings, "use_mock_google_oauth", mock_oauth)
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", jwt_secret)
    monkeypatch.setattr(main_module.settings, "oidc_issuer", oidc_issuer)
    monkeypatch.setattr(main_module.settings, "oidc_audience", oidc_audience)
    monkeypatch.setattr(main_module.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(main_module.settings, "oidc_shared_secret", oidc_shared_secret)
    monkeypatch.setattr(main_module.settings, "saml_idp_metadata_url", saml_metadata)
    monkeypatch.setattr(main_module.settings, "saml_sp_entity_id", saml_entity)
    monkeypatch.setattr(main_module.settings, "egress_allowed_hosts", egress_allowlist)
    monkeypatch.setattr(main_module.settings, "slm_base_url", slm_base_url)
    monkeypatch.setattr(main_module.settings, "service_mtls_enabled", True)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_cert_path", cert_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_key_path", key_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_ca_bundle_path", ca_path)
    monkeypatch.setenv("JWT_SECRET_KEY", jwt_secret)
    monkeypatch.setenv("OIDC_SHARED_SECRET", oidc_shared_secret)

    if should_raise:
        with pytest.raises(RuntimeError):
            main_module.enforce_startup_security()
    else:
        main_module.enforce_startup_security()


@pytest.mark.parametrize(
    "issuer,period,window",
    [
        ("", 30, 1),
        ("ZTA-AI", 10, 1),
        ("ZTA-AI", 30, -1),
        ("ZTA-AI", 30, 6),
    ],
)
def test_enforce_startup_security_rejects_invalid_mfa_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    issuer: str,
    period: int,
    window: int,
) -> None:
    reload(main_module)
    cert_path, key_path, ca_path = _create_mtls_artifacts(tmp_path)

    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "secrets_backend", "env")
    monkeypatch.setattr(main_module.settings, "auth_provider", "oidc")
    monkeypatch.setattr(main_module.settings, "use_mock_google_oauth", False)
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", "x" * 64)
    monkeypatch.setattr(main_module.settings, "oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(main_module.settings, "oidc_audience", "zta-backend")
    monkeypatch.setattr(main_module.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(main_module.settings, "oidc_shared_secret", "oidc-test-secret")
    monkeypatch.setattr(main_module.settings, "egress_allowed_hosts", "integrate.api.nvidia.com")
    monkeypatch.setattr(main_module.settings, "slm_base_url", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(main_module.settings, "service_mtls_enabled", True)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_cert_path", cert_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_key_path", key_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_ca_bundle_path", ca_path)
    monkeypatch.setattr(main_module.settings, "mfa_totp_issuer", issuer)
    monkeypatch.setattr(main_module.settings, "mfa_totp_period_seconds", period)
    monkeypatch.setattr(main_module.settings, "mfa_totp_window_steps", window)
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("OIDC_SHARED_SECRET", "oidc-test-secret")

    with pytest.raises(RuntimeError):
        main_module.enforce_startup_security()


def test_enforce_startup_security_requires_mtls_enabled_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reload(main_module)

    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "secrets_backend", "env")
    monkeypatch.setattr(main_module.settings, "auth_provider", "oidc")
    monkeypatch.setattr(main_module.settings, "use_mock_google_oauth", False)
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", "x" * 64)
    monkeypatch.setattr(main_module.settings, "oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(main_module.settings, "oidc_audience", "zta-backend")
    monkeypatch.setattr(main_module.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(main_module.settings, "oidc_shared_secret", "oidc-test-secret")
    monkeypatch.setattr(main_module.settings, "egress_allowed_hosts", "integrate.api.nvidia.com")
    monkeypatch.setattr(main_module.settings, "slm_base_url", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(main_module.settings, "mfa_totp_issuer", "ZTA-AI")
    monkeypatch.setattr(main_module.settings, "mfa_totp_period_seconds", 30)
    monkeypatch.setattr(main_module.settings, "mfa_totp_window_steps", 1)
    monkeypatch.setattr(main_module.settings, "service_mtls_enabled", False)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_cert_path", "")
    monkeypatch.setattr(main_module.settings, "service_mtls_client_key_path", "")
    monkeypatch.setattr(main_module.settings, "service_mtls_ca_bundle_path", "")
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("OIDC_SHARED_SECRET", "oidc-test-secret")

    with pytest.raises(RuntimeError):
        main_module.enforce_startup_security()


def test_enforce_startup_security_rejects_missing_mtls_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reload(main_module)

    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "secrets_backend", "env")
    monkeypatch.setattr(main_module.settings, "auth_provider", "oidc")
    monkeypatch.setattr(main_module.settings, "use_mock_google_oauth", False)
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", "x" * 64)
    monkeypatch.setattr(main_module.settings, "oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(main_module.settings, "oidc_audience", "zta-backend")
    monkeypatch.setattr(main_module.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(main_module.settings, "oidc_shared_secret", "oidc-test-secret")
    monkeypatch.setattr(main_module.settings, "egress_allowed_hosts", "integrate.api.nvidia.com")
    monkeypatch.setattr(main_module.settings, "slm_base_url", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(main_module.settings, "mfa_totp_issuer", "ZTA-AI")
    monkeypatch.setattr(main_module.settings, "mfa_totp_period_seconds", 30)
    monkeypatch.setattr(main_module.settings, "mfa_totp_window_steps", 1)
    monkeypatch.setattr(main_module.settings, "service_mtls_enabled", True)
    monkeypatch.setattr(
        main_module.settings,
        "service_mtls_client_cert_path",
        "/tmp/does-not-exist-client.crt",
    )
    monkeypatch.setattr(
        main_module.settings,
        "service_mtls_client_key_path",
        "/tmp/does-not-exist-client.key",
    )
    monkeypatch.setattr(
        main_module.settings,
        "service_mtls_ca_bundle_path",
        "/tmp/does-not-exist-ca.crt",
    )
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("OIDC_SHARED_SECRET", "oidc-test-secret")

    with pytest.raises(RuntimeError):
        main_module.enforce_startup_security()


def test_enforce_startup_security_rejects_disabled_zero_learning_in_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    reload(main_module)
    cert_path, key_path, ca_path = _create_mtls_artifacts(tmp_path)

    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "secrets_backend", "env")
    monkeypatch.setattr(main_module.settings, "auth_provider", "oidc")
    monkeypatch.setattr(main_module.settings, "use_mock_google_oauth", False)
    monkeypatch.setattr(main_module.settings, "jwt_secret_key", "x" * 64)
    monkeypatch.setattr(main_module.settings, "oidc_issuer", "https://idp.example.com")
    monkeypatch.setattr(main_module.settings, "oidc_audience", "zta-backend")
    monkeypatch.setattr(main_module.settings, "oidc_jwks_url", "")
    monkeypatch.setattr(main_module.settings, "oidc_shared_secret", "oidc-test-secret")
    monkeypatch.setattr(main_module.settings, "egress_allowed_hosts", "integrate.api.nvidia.com")
    monkeypatch.setattr(main_module.settings, "slm_base_url", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(main_module.settings, "mfa_totp_issuer", "ZTA-AI")
    monkeypatch.setattr(main_module.settings, "mfa_totp_period_seconds", 30)
    monkeypatch.setattr(main_module.settings, "mfa_totp_window_steps", 1)
    monkeypatch.setattr(main_module.settings, "service_mtls_enabled", True)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_cert_path", cert_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_client_key_path", key_path)
    monkeypatch.setattr(main_module.settings, "service_mtls_ca_bundle_path", ca_path)
    monkeypatch.setattr(main_module.settings, "slm_zero_learning_enforced", False)
    monkeypatch.setenv("JWT_SECRET_KEY", "x" * 64)
    monkeypatch.setenv("OIDC_SHARED_SECRET", "oidc-test-secret")

    with pytest.raises(RuntimeError):
        main_module.enforce_startup_security()
