from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.core.secret_manager import SecretManager, validate_secret_store_configuration


def _settings(**overrides):
    defaults = {
        "secrets_backend": "env",
        "secrets_cache_ttl_seconds": 300,
        "secrets_file_path": "",
        "vault_addr": "",
        "vault_token": "",
        "vault_token_env_var": "VAULT_TOKEN",
        "vault_kv_mount": "secret",
        "aws_secrets_manager_region": "",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_secret_manager_reads_file_backend(tmp_path) -> None:
    secrets_path = tmp_path / "secrets.json"
    secrets_path.write_text(
        json.dumps({"JWT_SECRET_KEY": "file-secret-value"}),
        encoding="utf-8",
    )

    manager = SecretManager(
        settings=_settings(secrets_backend="file", secrets_file_path=str(secrets_path))
    )

    assert manager.get_secret("JWT_SECRET_KEY") == "file-secret-value"


def test_secret_manager_uses_env_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET_KEY", "env-secret-value")
    manager = SecretManager(settings=_settings(secrets_backend="env"))

    assert manager.get_secret("JWT_SECRET_KEY", fallback="fallback") == "env-secret-value"


def test_validate_secret_store_configuration_rejects_missing_file_path() -> None:
    with pytest.raises(RuntimeError):
        validate_secret_store_configuration(_settings(secrets_backend="file"))


def test_validate_secret_store_configuration_rejects_vault_missing_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VAULT_TOKEN", raising=False)

    with pytest.raises(RuntimeError):
        validate_secret_store_configuration(
            _settings(
                secrets_backend="vault",
                vault_addr="http://localhost:8200",
                vault_token="",
                vault_token_env_var="VAULT_TOKEN",
                vault_kv_mount="secret",
            )
        )
