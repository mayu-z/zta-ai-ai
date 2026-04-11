from __future__ import annotations

import base64
import json
import os
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


class SecretManager:
    def __init__(self, settings: Any | None = None) -> None:
        self.settings = settings or get_settings()
        self._cache: dict[str, tuple[str, float]] = {}

    def _cache_ttl_seconds(self) -> int:
        ttl = int(getattr(self.settings, "secrets_cache_ttl_seconds", 300))
        return max(0, ttl)

    def _get_cached(self, key: str) -> str | None:
        entry = self._cache.get(key)
        if entry is None:
            return None

        value, expires_at = entry
        if expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return value

    def _set_cached(self, key: str, value: str) -> None:
        ttl = self._cache_ttl_seconds()
        if ttl <= 0:
            return

        self._cache[key] = (value, time.time() + ttl)

    def invalidate(self) -> None:
        self._cache.clear()

    def get_secret(self, secret_name: str, fallback: str = "") -> str:
        backend = str(getattr(self.settings, "secrets_backend", "env")).strip().lower()
        if backend != "env":
            cached = self._get_cached(secret_name)
            if cached is not None:
                return cached

        if backend == "env":
            value = self._read_from_env(secret_name)
        elif backend == "file":
            value = self._read_from_file(secret_name)
        elif backend == "vault":
            value = self._read_from_vault(secret_name)
        elif backend == "aws_secrets_manager":
            value = self._read_from_aws_secrets_manager(secret_name)
        else:
            raise RuntimeError(
                "SECRETS_BACKEND must be one of: env, file, vault, aws_secrets_manager"
            )

        if value:
            resolved = str(value)
            if backend != "env":
                self._set_cached(secret_name, resolved)
            return resolved

        resolved = str(fallback)
        return resolved

    def get_csv_secret(self, secret_name: str, fallback_csv: str = "") -> list[str]:
        raw = self.get_secret(secret_name, fallback=fallback_csv)
        return [item.strip() for item in raw.split(",") if item.strip()]

    def _read_from_env(self, secret_name: str) -> str:
        return os.getenv(secret_name, "")

    def _read_from_file(self, secret_name: str) -> str:
        file_path = str(getattr(self.settings, "secrets_file_path", "")).strip()
        if not file_path:
            return ""

        path = Path(file_path)
        if not path.is_file():
            raise RuntimeError(
                f"SECRETS_FILE_PATH must point to an existing file: {file_path}"
            )

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Failed to parse secrets file as JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Secrets file must contain a JSON object")

        value = payload.get(secret_name)
        if value is None:
            return ""
        return str(value)

    def _read_from_vault(self, secret_name: str) -> str:
        vault_addr = str(getattr(self.settings, "vault_addr", "")).strip()
        if not vault_addr:
            raise RuntimeError("VAULT_ADDR is required when SECRETS_BACKEND=vault")

        token = str(getattr(self.settings, "vault_token", "")).strip()
        token_env_var = str(
            getattr(self.settings, "vault_token_env_var", "VAULT_TOKEN")
        ).strip() or "VAULT_TOKEN"
        if not token:
            token = os.getenv(token_env_var, "")
        if not token:
            raise RuntimeError(
                f"VAULT_TOKEN or {token_env_var} is required when SECRETS_BACKEND=vault"
            )

        mount = str(getattr(self.settings, "vault_kv_mount", "secret")).strip()
        prefix = str(getattr(self.settings, "vault_secret_path_prefix", "zta-ai/")).strip()

        normalized_prefix = prefix.strip("/")
        suffix = secret_name.lower()
        full_path = f"{normalized_prefix}/{suffix}" if normalized_prefix else suffix
        url = f"{vault_addr.rstrip('/')}/v1/{mount.strip('/')}/data/{full_path}"

        with httpx.Client(timeout=5.0) as client:
            response = client.get(url, headers={"X-Vault-Token": token})

        if response.status_code == 404:
            return ""

        try:
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Vault secret read failed") from exc

        payload = response.json()
        data = payload.get("data", {}).get("data", {})
        if not isinstance(data, dict):
            return ""

        if secret_name in data:
            return str(data.get(secret_name) or "")
        if secret_name.lower() in data:
            return str(data.get(secret_name.lower()) or "")
        if "value" in data:
            return str(data.get("value") or "")
        return ""

    def _read_from_aws_secrets_manager(self, secret_name: str) -> str:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError(
                "boto3 is required for SECRETS_BACKEND=aws_secrets_manager"
            ) from exc

        region = str(getattr(self.settings, "aws_secrets_manager_region", "")).strip()
        if not region:
            raise RuntimeError(
                "AWS_SECRETS_MANAGER_REGION is required when SECRETS_BACKEND=aws_secrets_manager"
            )

        prefix = str(getattr(self.settings, "aws_secrets_manager_prefix", "")).strip()
        secret_id = f"{prefix}{secret_name}"

        client = boto3.client("secretsmanager", region_name=region)
        try:
            result = client.get_secret_value(SecretId=secret_id)
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("AWS Secrets Manager secret read failed") from exc

        secret_string = result.get("SecretString")
        if secret_string:
            try:
                decoded = json.loads(secret_string)
                if isinstance(decoded, dict):
                    if secret_name in decoded:
                        return str(decoded.get(secret_name) or "")
                    if "value" in decoded:
                        return str(decoded.get("value") or "")
            except Exception:  # noqa: BLE001
                pass
            return str(secret_string)

        secret_binary = result.get("SecretBinary")
        if isinstance(secret_binary, (bytes, bytearray)):
            return base64.b64decode(secret_binary).decode("utf-8")

        return ""


def validate_secret_store_configuration(settings: Any) -> None:
    backend = str(getattr(settings, "secrets_backend", "env")).strip().lower()
    allowed = {"env", "file", "vault", "aws_secrets_manager"}
    if backend not in allowed:
        raise RuntimeError(
            "SECRETS_BACKEND must be one of: env, file, vault, aws_secrets_manager"
        )

    if backend == "file":
        file_path = str(getattr(settings, "secrets_file_path", "")).strip()
        if not file_path:
            raise RuntimeError(
                "SECRETS_FILE_PATH is required when SECRETS_BACKEND=file"
            )
        if not Path(file_path).is_file():
            raise RuntimeError(
                f"SECRETS_FILE_PATH must point to an existing file: {file_path}"
            )

    if backend == "vault":
        vault_addr = str(getattr(settings, "vault_addr", "")).strip()
        if not vault_addr:
            raise RuntimeError("VAULT_ADDR is required when SECRETS_BACKEND=vault")

        token = str(getattr(settings, "vault_token", "")).strip()
        token_env_var = str(
            getattr(settings, "vault_token_env_var", "VAULT_TOKEN")
        ).strip() or "VAULT_TOKEN"
        if not token and not os.getenv(token_env_var, ""):
            raise RuntimeError(
                f"VAULT_TOKEN or {token_env_var} is required when SECRETS_BACKEND=vault"
            )

        kv_mount = str(getattr(settings, "vault_kv_mount", "")).strip()
        if not kv_mount:
            raise RuntimeError("VAULT_KV_MOUNT is required when SECRETS_BACKEND=vault")

    if backend == "aws_secrets_manager":
        region = str(getattr(settings, "aws_secrets_manager_region", "")).strip()
        if not region:
            raise RuntimeError(
                "AWS_SECRETS_MANAGER_REGION is required when SECRETS_BACKEND=aws_secrets_manager"
            )


@lru_cache(maxsize=1)
def get_secret_manager() -> SecretManager:
    return SecretManager()


secret_manager = get_secret_manager()
