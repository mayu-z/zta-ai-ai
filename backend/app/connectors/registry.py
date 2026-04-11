from __future__ import annotations

import base64
import json
from typing import Any

from app.connectors.external_connectors import ERPNextConnector, GoogleSheetsConnector
from app.connectors.mock_claims import mock_claims_connector
from app.connectors.source_types import (
    SQL_CONNECTOR_TYPES,
    is_local_store_source_type,
)
from app.connectors.sql_connector import SQLConnector
from app.core.exceptions import ValidationError
from app.db.models import DataSource
from app.schemas.pipeline import CompiledQueryPlan


class ConnectorRegistry:
    def get(
        self,
        plan: CompiledQueryPlan,
        data_source: DataSource | None = None,
    ):
        source_type = str(plan.source_type).strip().lower()

        # Local immutable store sources are served by the trusted in-process connector.
        if is_local_store_source_type(source_type):
            return mock_claims_connector

        if source_type in SQL_CONNECTOR_TYPES:
            source = self._require_data_source(source_type, data_source)
            return self._build_sql_connector(source_type, source)

        if source_type == "erpnext":
            source = self._require_data_source(source_type, data_source)
            config = self._decode_source_config(source)
            required = ("base_url", "api_key", "api_secret")
            missing = [key for key in required if not self._first_non_empty(config, key)]
            if missing:
                raise ValidationError(
                    message=f"erpnext source config missing required fields: {', '.join(missing)}",
                    code="SOURCE_CONFIG_INVALID",
                )
            doctype = self._first_non_empty(config, "doctype") or "ZTA Claim"
            verify_tls_raw = config.get("verify_tls")
            verify_tls = True if verify_tls_raw is None else bool(verify_tls_raw)
            seeded_rows = config.get("seeded_rows") if isinstance(config.get("seeded_rows"), list) else None
            field_map = config.get("field_map") if isinstance(config.get("field_map"), dict) else None
            max_retries_raw = config.get("max_retries", 1)
            try:
                max_retries = int(max_retries_raw)
            except Exception:  # noqa: BLE001
                max_retries = 1

            return ERPNextConnector(
                base_url=str(config["base_url"]).strip(),
                api_key=str(config["api_key"]).strip(),
                api_secret=str(config["api_secret"]).strip(),
                doctype=doctype,
                field_map=field_map,
                verify_tls=verify_tls,
                seeded_rows=seeded_rows,
                max_retries=max_retries,
            )

        if source_type == "google_sheets":
            source = self._require_data_source(source_type, data_source)
            config = self._decode_source_config(source)
            service_account = config.get("service_account_json")
            if not isinstance(service_account, dict) or not service_account:
                raise ValidationError(
                    message=f"{source_type} source requires a non-empty service_account_json object",
                    code="SOURCE_CONFIG_INVALID",
                )
            spreadsheet_id = self._first_non_empty(
                config,
                "spreadsheet_id",
                "sheet_id",
            )
            if not spreadsheet_id:
                raise ValidationError(
                    message="google_sheets source requires spreadsheet_id",
                    code="SOURCE_CONFIG_INVALID",
                )

            sheet_rows = config.get("sheet_rows", config.get("rows"))
            return GoogleSheetsConnector(
                service_account_json=service_account,
                spreadsheet_id=spreadsheet_id,
                sheet_rows=sheet_rows,
            )

        if source_type == "google_drive":
            raise ValidationError(
                message="Source type 'google_drive' is recognized but live query execution is not enabled yet",
                code="SOURCE_CONNECTOR_NOT_IMPLEMENTED",
            )

        raise ValidationError(
            message=f"No execution adapter is enabled for source type '{source_type}'",
            code="SOURCE_CONNECTOR_NOT_ENABLED",
        )

    def _require_data_source(
        self,
        source_type: str,
        data_source: DataSource | None,
    ) -> DataSource:
        if data_source is None:
            raise ValidationError(
                message=f"Source type '{source_type}' requires a bound data_source_id",
                code="SOURCE_DATA_SOURCE_REQUIRED",
            )
        return data_source

    def _decode_source_config(self, source: DataSource) -> dict[str, Any]:
        raw = (source.config_encrypted or "").strip()
        if not raw:
            return {}

        try:
            decoded = base64.b64decode(raw).decode("utf-8")
            payload = json.loads(decoded)
        except Exception as exc:  # noqa: BLE001
            raise ValidationError(
                message="Data source configuration could not be decoded",
                code="SOURCE_CONFIG_DECODE_FAILED",
            ) from exc

        if not isinstance(payload, dict):
            raise ValidationError(
                message="Data source configuration must decode to an object",
                code="SOURCE_CONFIG_INVALID",
            )
        return payload

    def _build_sql_connector(self, source_type: str, source: DataSource) -> SQLConnector:
        config = self._decode_source_config(source)
        connection_url = self._first_non_empty(
            config,
            "connection_url",
            "database_url",
            "dsn",
        )
        if not connection_url:
            raise ValidationError(
                message=f"{source_type} source requires one of: connection_url, database_url, dsn",
                code="SOURCE_CONFIG_INVALID",
            )

        claims_table = self._first_non_empty(
            config,
            "records_table",
            "claims_table",
            "table_name",
            "table",
        ) or "claims"
        claims_schema = self._first_non_empty(
            config,
            "records_schema",
            "claims_schema",
            "schema",
        )
        column_map_raw = config.get("column_map")
        if column_map_raw is not None and not isinstance(column_map_raw, dict):
            raise ValidationError(
                message="column_map must be an object",
                code="SOURCE_CONFIG_INVALID",
            )

        return SQLConnector(
            connection_url=connection_url,
            claims_table=claims_table,
            claims_schema=claims_schema,
            column_map=column_map_raw,
        )

    def _first_non_empty(self, data: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None


connector_registry = ConnectorRegistry()
