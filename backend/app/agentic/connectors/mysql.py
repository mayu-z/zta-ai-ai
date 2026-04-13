from __future__ import annotations

from typing import Any

from app.core.secret_manager import secret_manager

from .postgres import PostgresConnector


class MySQLConnector(PostgresConnector):
    """MySQL connector with the same execution guarantees as PostgresConnector."""

    def __init__(self, tenant_id, config: dict[str, Any]):
        self._dialect = str(config.get("source_dialect") or "mysql").strip().lower()
        super().__init__(tenant_id=tenant_id, config=config)

    def _resolve_connection_url(self) -> str:
        key_prefix = "mariadb" if self._dialect == "mariadb" else "mysql"
        secret_key = f"{key_prefix}:{self.tenant_id}"
        fallback = str(self._config.get("connection_url") or self._config.get("database_url") or "")
        raw = secret_manager.get_secret(secret_key, fallback=fallback).strip()
        if raw.startswith("mysql://"):
            return "mysql+aiomysql://" + raw[len("mysql://") :]
        if raw.startswith("mariadb://"):
            return "mysql+aiomysql://" + raw[len("mariadb://") :]
        if raw.startswith("mysql+pymysql://"):
            return "mysql+aiomysql://" + raw[len("mysql+pymysql://") :]
        if raw.startswith("mysql+"):
            return raw
        return raw


MariaDBConnector = MySQLConnector
