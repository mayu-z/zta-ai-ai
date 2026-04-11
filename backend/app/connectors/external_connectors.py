from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
import time
from typing import Any
from urllib.parse import quote

import httpx

from sqlalchemy.orm import Session

from app.connectors.base import (
    ConnectionInfo,
    ConnectionStatus,
    ConnectorBase,
    HealthStatus,
    SyncResult,
)
from app.core.exceptions import ValidationError
from app.schemas.pipeline import CompiledQueryPlan


class ERPNextConnector(ConnectorBase):
    REQUIRED_ROW_KEYS = {"tenant_id", "domain", "entity_type", "claim_key"}
    DEFAULT_FIELD_MAP = {
        "tenant_id": "tenant_id",
        "domain": "domain",
        "entity_type": "entity_type",
        "claim_key": "claim_key",
        "owner_id": "owner_id",
        "department_id": "department_id",
        "course_id": "course_id",
        "admin_function": "admin_function",
        "value_number": "value_number",
        "value_text": "value_text",
        "value_json": "value_json",
    }

    def __init__(
        self,
        base_url: str,
        api_key: str,
        api_secret: str,
        doctype: str = "ZTA Claim",
        field_map: dict[str, str] | None = None,
        verify_tls: bool = True,
        seeded_rows: list[dict[str, Any]] | None = None,
        max_retries: int = 1,
    ) -> None:
        normalized_base_url = str(base_url).strip().rstrip("/")
        if not normalized_base_url.startswith(("http://", "https://")):
            raise ValidationError(
                message="ERPNext base_url must be an absolute http(s) URL",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized_api_key = str(api_key).strip()
        normalized_api_secret = str(api_secret).strip()
        if not normalized_api_key or not normalized_api_secret:
            raise ValidationError(
                message="ERPNext connector requires non-empty api_key and api_secret",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized_doctype = str(doctype).strip()
        if not normalized_doctype:
            raise ValidationError(
                message="ERPNext connector requires a non-empty doctype",
                code="SOURCE_CONFIG_INVALID",
            )

        self.base_url = normalized_base_url
        self.api_key = normalized_api_key
        self.api_secret = normalized_api_secret
        self.doctype = normalized_doctype
        self.field_map = self._build_field_map(field_map or {})
        self.verify_tls = bool(verify_tls)
        self.seeded_rows = self._normalize_rows(seeded_rows)
        self.max_retries = max(int(max_retries), 0)

        self._last_query_latency_ms = 0
        self._consecutive_failures = 0
        self._last_failure_at: str | None = None

    def connect(self, timeout_seconds: int = 30) -> ConnectionStatus:
        if timeout_seconds <= 0:
            raise ValidationError(
                message="timeout_seconds must be greater than 0",
                code="SOURCE_CONNECT_TIMEOUT_INVALID",
            )

        started = time.perf_counter()
        try:
            if not self.seeded_rows:
                self._request_json(
                    method="GET",
                    path="/api/method/ping",
                    timeout_seconds=timeout_seconds,
                    error_code="SOURCE_CONNECT_FAILED",
                    error_message="Unable to connect to ERPNext source",
                )

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_success(elapsed_ms)
            return ConnectionStatus(status="connected", response_time_ms=elapsed_ms)
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_failure(elapsed_ms)
            raise

    def discover_schema(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        if self.seeded_rows:
            fields = sorted(
                {
                    key
                    for row in self.seeded_rows
                    for key in row.keys()
                }
            )
            return [
                {
                    "entity": self.doctype,
                    "fields": [
                        {"name": field_name, "type": self._infer_field_type(field_name)}
                        for field_name in fields
                    ],
                }
            ]

        payload = self._request_json(
            method="GET",
            path=f"/api/resource/{self._doctype_path()}",
            timeout_seconds=60,
            params={
                "fields": json.dumps(sorted(set(self.field_map.values()))),
                "limit_page_length": "1",
            },
            error_code="SOURCE_SCHEMA_DISCOVERY_FAILED",
            error_message="Failed to discover ERPNext schema",
        )
        rows = self._extract_data_rows(payload, "SOURCE_SCHEMA_DISCOVERY_FAILED")
        first = rows[0] if rows else {}
        field_names = sorted(set(first.keys()) if isinstance(first, dict) else set(self.field_map.values()))

        return [
            {
                "entity": self.doctype,
                "fields": [
                    {
                        "name": field_name,
                        "type": self._infer_field_type_from_value(first.get(field_name)),
                    }
                    for field_name in field_names
                ],
            }
        ]

    def execute_query(
        self,
        db: Session,
        plan: CompiledQueryPlan,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValidationError(
                message="timeout_seconds must be greater than 0",
                code="SOURCE_QUERY_TIMEOUT_INVALID",
            )

        started = time.perf_counter()
        try:
            if self.seeded_rows:
                candidate_rows = list(self.seeded_rows)
            else:
                payload = self._request_json(
                    method="GET",
                    path=f"/api/resource/{self._doctype_path()}",
                    timeout_seconds=timeout_seconds,
                    params={
                        "fields": json.dumps(self._query_fields()),
                        "filters": json.dumps(
                            self._query_filters(
                                filters=plan.filters,
                                select_keys=plan.select_keys,
                            )
                        ),
                        "limit_page_length": "5000",
                    },
                    error_code="SOURCE_QUERY_FAILED",
                    error_message="ERPNext source query execution failed",
                )
                rows = self._extract_data_rows(payload, "SOURCE_QUERY_FAILED")
                candidate_rows = [self._canonicalize_row(row) for row in rows if isinstance(row, dict)]

            filters = plan.filters
            selected_keys = set(plan.select_keys)
            scoped_rows = [
                row
                for row in candidate_rows
                if self._row_matches_scope(
                    row=row,
                    filters=filters,
                    selected_keys=selected_keys,
                )
            ]
            if not scoped_rows:
                raise ValidationError(
                    message="No records matched this scoped query",
                    code="NO_CLAIMS_FOUND",
                )

            grouped: dict[str, list[Any]] = defaultdict(list)
            for row in scoped_rows:
                claim_key = str(row["claim_key"])
                grouped[claim_key].append(self._extract_claim_value(row))

            result: dict[str, Any] = {}
            for claim_key, values in grouped.items():
                result[claim_key] = self._reduce_values(
                    claim_key=claim_key,
                    values=values,
                    requires_aggregate=plan.requires_aggregate,
                )

            for expected_key in plan.select_keys:
                result.setdefault(expected_key, None)

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_success(elapsed_ms)
            return result
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_failure(elapsed_ms)
            raise

    def sync(self) -> SyncResult:
        started = time.perf_counter()
        try:
            schema = self.discover_schema(force_refresh=False)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return SyncResult(
                status="complete",
                tables_discovered=len(schema),
                tables_added=0,
                tables_removed=0,
                fields_changed=0,
                duration_ms=elapsed_ms,
                errors=[],
            )
        except ValidationError as exc:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return SyncResult(
                status="failed",
                tables_discovered=0,
                tables_added=0,
                tables_removed=0,
                fields_changed=0,
                duration_ms=elapsed_ms,
                errors=[exc.message],
            )

    def health_check(self) -> HealthStatus:
        try:
            self.connect(timeout_seconds=5)
            recommendation = "No action required"
            status = "healthy"
        except ValidationError as exc:
            recommendation = exc.message
            status = "error"

        return HealthStatus(
            status=status,
            last_query_latency_ms=self._last_query_latency_ms,
            consecutive_failures=self._consecutive_failures,
            last_failure_at=self._last_failure_at,
            recommendation=recommendation,
        )

    def _record_success(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures = 0
        self._last_failure_at = None

    def _record_failure(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures += 1
        self._last_failure_at = datetime.now(tz=UTC).isoformat()

    def _doctype_path(self) -> str:
        return quote(self.doctype, safe="")

    def _auth_headers(self) -> dict[str, str]:
        return {
            "Authorization": f"token {self.api_key}:{self.api_secret}",
            "Accept": "application/json",
        }

    def _request_json(
        self,
        *,
        method: str,
        path: str,
        timeout_seconds: int,
        error_code: str,
        error_message: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        retries = self.max_retries + 1

        for attempt in range(retries):
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    headers=self._auth_headers(),
                    timeout=timeout_seconds,
                    verify=self.verify_tls,
                ) as client:
                    response = client.request(method=method, url=path, params=params)

                if response.status_code in {429, 500, 502, 503, 504} and attempt < self.max_retries:
                    continue

                if response.status_code == 401:
                    raise ValidationError(
                        message="ERPNext authentication failed",
                        code="SOURCE_AUTHENTICATION_FAILED",
                    )
                if response.status_code == 403:
                    raise ValidationError(
                        message="ERPNext authorization denied",
                        code="SOURCE_AUTHORIZATION_FAILED",
                    )
                if response.status_code == 404:
                    raise ValidationError(
                        message="ERPNext resource was not found",
                        code="SOURCE_NOT_FOUND",
                    )
                if response.status_code == 429:
                    raise ValidationError(
                        message="ERPNext connector rate limit exceeded",
                        code="SOURCE_RATE_LIMITED",
                    )

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValidationError(
                        message="ERPNext response payload must be an object",
                        code="SOURCE_RESPONSE_INVALID",
                    )
                return payload
            except ValidationError as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise
            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ValidationError(
                        message="ERPNext request timed out",
                        code="SOURCE_TIMEOUT",
                    ) from exc
            except (httpx.HTTPError, ValueError) as exc:
                last_exc = exc
                if attempt >= self.max_retries:
                    raise ValidationError(
                        message=error_message,
                        code=error_code,
                    ) from exc

        raise ValidationError(
            message=error_message,
            code=error_code,
        ) from last_exc

    def _build_field_map(self, custom: dict[str, str]) -> dict[str, str]:
        mapped = dict(self.DEFAULT_FIELD_MAP)
        allowed = set(self.DEFAULT_FIELD_MAP.keys())

        for key, value in custom.items():
            normalized_key = str(key).strip()
            if normalized_key not in allowed:
                raise ValidationError(
                    message=f"Invalid ERP field_map key '{normalized_key}'",
                    code="SOURCE_CONFIG_INVALID",
                )
            normalized_value = str(value).strip()
            if not normalized_value:
                raise ValidationError(
                    message=f"ERP field_map value for '{normalized_key}' cannot be empty",
                    code="SOURCE_CONFIG_INVALID",
                )
            mapped[normalized_key] = normalized_value
        return mapped

    def _normalize_rows(self, rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if rows is None:
            return []
        if not isinstance(rows, list):
            raise ValidationError(
                message="ERP seeded_rows must be an array of objects",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ValidationError(
                    message=f"seeded_rows[{idx}] must be an object",
                    code="SOURCE_CONFIG_INVALID",
                )

            missing = [
                key
                for key in self.REQUIRED_ROW_KEYS
                if row.get(key) is None or str(row.get(key)).strip() == ""
            ]
            if missing:
                raise ValidationError(
                    message=f"seeded_rows[{idx}] missing required keys: {', '.join(sorted(missing))}",
                    code="SOURCE_CONFIG_INVALID",
                )

            normalized.append(dict(row))

        return normalized

    def _extract_data_rows(self, payload: dict[str, Any], error_code: str) -> list[dict[str, Any]]:
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ValidationError(
                message="ERPNext response is missing a valid data array",
                code=error_code,
            )
        return [row for row in rows if isinstance(row, dict)]

    def _query_fields(self) -> list[str]:
        required = {
            self.field_map["tenant_id"],
            self.field_map["domain"],
            self.field_map["entity_type"],
            self.field_map["claim_key"],
            self.field_map["owner_id"],
            self.field_map["department_id"],
            self.field_map["course_id"],
            self.field_map["admin_function"],
            self.field_map["value_number"],
            self.field_map["value_text"],
            self.field_map["value_json"],
        }
        return sorted(required)

    def _query_filters(
        self,
        *,
        filters: dict[str, Any],
        select_keys: list[str],
    ) -> list[list[Any]]:
        query_filters: list[list[Any]] = [
            [self.field_map["tenant_id"], "=", str(filters["tenant_id"])],
            [self.field_map["domain"], "=", str(filters["domain"])],
            [self.field_map["entity_type"], "=", str(filters["entity_type"])],
            [self.field_map["claim_key"], "in", list(select_keys)],
        ]

        if filters.get("owner_id"):
            query_filters.append([self.field_map["owner_id"], "=", str(filters["owner_id"])])
        if filters.get("department_id"):
            query_filters.append(
                [self.field_map["department_id"], "=", str(filters["department_id"])]
            )
        if filters.get("admin_function"):
            query_filters.append(
                [self.field_map["admin_function"], "=", str(filters["admin_function"])]
            )

        course_ids = filters.get("course_ids")
        if isinstance(course_ids, list) and course_ids:
            query_filters.append([self.field_map["course_id"], "in", [str(v) for v in course_ids]])

        return query_filters

    def _canonicalize_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "tenant_id": row.get(self.field_map["tenant_id"]),
            "domain": row.get(self.field_map["domain"]),
            "entity_type": row.get(self.field_map["entity_type"]),
            "claim_key": row.get(self.field_map["claim_key"]),
            "owner_id": row.get(self.field_map["owner_id"]),
            "department_id": row.get(self.field_map["department_id"]),
            "course_id": row.get(self.field_map["course_id"]),
            "admin_function": row.get(self.field_map["admin_function"]),
            "value_number": self._coerce_numeric(row.get(self.field_map["value_number"])),
            "value_text": row.get(self.field_map["value_text"]),
            "value_json": row.get(self.field_map["value_json"]),
        }

    @staticmethod
    def _coerce_numeric(value: Any) -> int | float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str) and value.strip():
            text = value.strip()
            try:
                if any(token in text for token in (".", "e", "E")):
                    return float(text)
                return int(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _row_matches_scope(
        *,
        row: dict[str, Any],
        filters: dict[str, Any],
        selected_keys: set[str],
    ) -> bool:
        if str(row.get("tenant_id")) != str(filters["tenant_id"]):
            return False
        if str(row.get("domain")) != str(filters["domain"]):
            return False
        if str(row.get("entity_type")) != str(filters["entity_type"]):
            return False

        claim_key = str(row.get("claim_key") or "")
        if claim_key not in selected_keys:
            return False

        if filters.get("owner_id") and str(row.get("owner_id") or "") != str(filters["owner_id"]):
            return False
        if filters.get("department_id") and str(row.get("department_id") or "") != str(
            filters["department_id"]
        ):
            return False
        if filters.get("admin_function") and str(row.get("admin_function") or "") != str(
            filters["admin_function"]
        ):
            return False

        course_ids = filters.get("course_ids")
        if isinstance(course_ids, list) and course_ids:
            if str(row.get("course_id") or "") not in {str(course_id) for course_id in course_ids}:
                return False

        return True

    def _infer_field_type(self, field_name: str) -> str:
        for row in self.seeded_rows:
            value = row.get(field_name)
            if value is None:
                continue
            return self._infer_field_type_from_value(value)
        return "unknown"

    @staticmethod
    def _infer_field_type_from_value(value: Any) -> str:
        if value is None:
            return "unknown"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, (int, float)):
            return "number"
        if isinstance(value, dict):
            return "object"
        if isinstance(value, list):
            return "array"
        return "string"

    @staticmethod
    def _extract_claim_value(row: dict[str, Any]) -> Any:
        if row.get("value_number") is not None:
            return row["value_number"]
        if row.get("value_text") is not None:
            return row["value_text"]
        if row.get("value_json") is not None:
            return row["value_json"]
        return None

    @staticmethod
    def _reduce_values(
        claim_key: str,
        values: list[Any],
        requires_aggregate: bool,
    ) -> Any:
        if not values:
            return None

        if not requires_aggregate:
            return values[0]

        non_null = [value for value in values if value is not None]
        numeric_values = [value for value in non_null if isinstance(value, (int, float))]

        if non_null and len(numeric_values) == len(non_null):
            average_markers = ("avg", "average", "percentage", "rate", "ratio", "gpa")
            if any(marker in claim_key.lower() for marker in average_markers):
                avg = sum(float(value) for value in numeric_values) / len(numeric_values)
                return round(avg, 2)

            total = sum(float(value) for value in numeric_values)
            if all(isinstance(value, int) for value in numeric_values):
                return int(total)
            return round(total, 2)

        return non_null[0] if non_null else None

    def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            connector_id="erpnext",
            tenant_id=None,
            source_type="erpnext",
            supports_sync=True,
            supports_live_queries=True,
        )


class GoogleSheetsConnector(ConnectorBase):
    REQUIRED_ROW_KEYS = {"tenant_id", "domain", "entity_type", "claim_key"}

    def __init__(
        self,
        service_account_json: dict[str, Any],
        spreadsheet_id: str,
        sheet_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        if not isinstance(service_account_json, dict) or not service_account_json:
            raise ValidationError(
                message="service_account_json must be a non-empty object",
                code="SOURCE_CONFIG_INVALID",
            )

        project_id = str(service_account_json.get("project_id") or "").strip()
        if not project_id:
            raise ValidationError(
                message="service_account_json.project_id is required",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized_spreadsheet_id = str(spreadsheet_id).strip()
        if not normalized_spreadsheet_id:
            raise ValidationError(
                message="spreadsheet_id is required for Google Sheets connectors",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized_rows = self._normalize_rows(sheet_rows)

        self.service_account_json = service_account_json
        self.spreadsheet_id = normalized_spreadsheet_id
        self.sheet_rows = normalized_rows
        self._last_query_latency_ms = 0
        self._consecutive_failures = 0
        self._last_failure_at: str | None = None

    def connect(self, timeout_seconds: int = 30) -> ConnectionStatus:
        if timeout_seconds <= 0:
            raise ValidationError(
                message="timeout_seconds must be greater than 0",
                code="SOURCE_CONNECT_TIMEOUT_INVALID",
            )
        return ConnectionStatus(status="connected", response_time_ms=0)

    def discover_schema(self, force_refresh: bool = False) -> list[dict[str, Any]]:
        fields = sorted(
            {
                key
                for row in self.sheet_rows
                for key in row.keys()
            }
        )
        if not fields:
            fields = sorted(
                self.REQUIRED_ROW_KEYS
                | {
                    "owner_id",
                    "department_id",
                    "course_id",
                    "admin_function",
                    "value_number",
                    "value_text",
                    "value_json",
                }
            )

        return [
            {
                "entity": "google_sheet_rows",
                "spreadsheet_id": self.spreadsheet_id,
                "fields": [
                    {"name": field_name, "type": self._infer_field_type(field_name)}
                    for field_name in fields
                ],
            }
        ]

    def execute_query(
        self,
        db: Session,
        plan: CompiledQueryPlan,
        timeout_seconds: int = 60,
    ) -> dict[str, Any]:
        if timeout_seconds <= 0:
            raise ValidationError(
                message="timeout_seconds must be greater than 0",
                code="SOURCE_QUERY_TIMEOUT_INVALID",
            )

        started = time.perf_counter()
        try:
            filters = plan.filters
            selected_keys = set(plan.select_keys)
            scoped_rows = []

            for row in self.sheet_rows:
                if str(row.get("tenant_id")) != str(filters["tenant_id"]):
                    continue
                if str(row.get("domain")) != str(filters["domain"]):
                    continue
                if str(row.get("entity_type")) != str(filters["entity_type"]):
                    continue

                claim_key = str(row.get("claim_key") or "")
                if claim_key not in selected_keys:
                    continue

                if filters.get("owner_id") and str(row.get("owner_id") or "") != str(
                    filters["owner_id"]
                ):
                    continue

                if filters.get("department_id") and str(
                    row.get("department_id") or ""
                ) != str(filters["department_id"]):
                    continue

                if filters.get("admin_function") and str(
                    row.get("admin_function") or ""
                ) != str(filters["admin_function"]):
                    continue

                course_ids = filters.get("course_ids")
                if isinstance(course_ids, list) and course_ids:
                    if str(row.get("course_id") or "") not in {
                        str(course_id) for course_id in course_ids
                    }:
                        continue

                scoped_rows.append(row)

            if not scoped_rows:
                raise ValidationError(
                    message="No records matched this scoped query",
                    code="NO_CLAIMS_FOUND",
                )

            grouped: dict[str, list[Any]] = defaultdict(list)
            for row in scoped_rows:
                claim_key = str(row["claim_key"])
                grouped[claim_key].append(self._extract_claim_value(row))

            result: dict[str, Any] = {}
            for claim_key, values in grouped.items():
                result[claim_key] = self._reduce_values(
                    claim_key=claim_key,
                    values=values,
                    requires_aggregate=plan.requires_aggregate,
                )

            for expected_key in plan.select_keys:
                result.setdefault(expected_key, None)

            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_success(elapsed_ms)
            return result
        except Exception:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            self._record_failure(elapsed_ms)
            raise

    def sync(self) -> SyncResult:
        started = time.perf_counter()
        schema = self.discover_schema(force_refresh=False)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return SyncResult(
            status="complete",
            tables_discovered=len(schema),
            tables_added=0,
            tables_removed=0,
            fields_changed=0,
            duration_ms=elapsed_ms,
            errors=[],
        )

    def health_check(self) -> HealthStatus:
        if self._consecutive_failures > 0:
            return HealthStatus(
                status="degraded",
                last_query_latency_ms=self._last_query_latency_ms,
                consecutive_failures=self._consecutive_failures,
                last_failure_at=self._last_failure_at,
                recommendation="Review recent query failures and retry after fixing source data",
            )

        status = "healthy" if self.sheet_rows else "degraded"
        recommendation = (
            "No action required"
            if self.sheet_rows
            else "Connector is live but sheet_rows is empty; sync source rows to enable query results"
        )
        return HealthStatus(
            status=status,
            last_query_latency_ms=self._last_query_latency_ms,
            consecutive_failures=self._consecutive_failures,
            last_failure_at=self._last_failure_at,
            recommendation=recommendation,
        )

    def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            connector_id="google_sheets",
            tenant_id=None,
            source_type="google_sheets",
            supports_sync=True,
            supports_live_queries=True,
        )

    def _normalize_rows(
        self,
        sheet_rows: list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if sheet_rows is None:
            return []
        if not isinstance(sheet_rows, list):
            raise ValidationError(
                message="sheet_rows must be an array of objects",
                code="SOURCE_CONFIG_INVALID",
            )

        normalized: list[dict[str, Any]] = []
        for idx, row in enumerate(sheet_rows):
            if not isinstance(row, dict):
                raise ValidationError(
                    message=f"sheet_rows[{idx}] must be an object",
                    code="SOURCE_CONFIG_INVALID",
                )

            missing = [
                key
                for key in self.REQUIRED_ROW_KEYS
                if row.get(key) is None or str(row.get(key)).strip() == ""
            ]
            if missing:
                raise ValidationError(
                    message=(
                        f"sheet_rows[{idx}] is missing required keys: {', '.join(sorted(missing))}"
                    ),
                    code="SOURCE_CONFIG_INVALID",
                )

            normalized.append(dict(row))

        return normalized

    def _infer_field_type(self, field_name: str) -> str:
        for row in self.sheet_rows:
            value = row.get(field_name)
            if value is None:
                continue
            if isinstance(value, bool):
                return "boolean"
            if isinstance(value, (int, float)):
                return "number"
            if isinstance(value, dict):
                return "object"
            if isinstance(value, list):
                return "array"
            return "string"
        return "unknown"

    def _record_success(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures = 0
        self._last_failure_at = None

    def _record_failure(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures += 1
        self._last_failure_at = datetime.now(tz=UTC).isoformat()

    @staticmethod
    def _extract_claim_value(row: dict[str, Any]) -> Any:
        if row.get("value_number") is not None:
            return row["value_number"]
        if row.get("value_text") is not None:
            return row["value_text"]
        if row.get("value_json") is not None:
            return row["value_json"]
        return None

    @staticmethod
    def _reduce_values(
        claim_key: str,
        values: list[Any],
        requires_aggregate: bool,
    ) -> Any:
        if not values:
            return None

        if not requires_aggregate:
            return values[0]

        non_null = [value for value in values if value is not None]
        numeric_values = [value for value in non_null if isinstance(value, (int, float))]

        if non_null and len(numeric_values) == len(non_null):
            average_markers = ("avg", "average", "percentage", "rate", "ratio", "gpa")
            if any(marker in claim_key.lower() for marker in average_markers):
                avg = sum(float(value) for value in numeric_values) / len(numeric_values)
                return round(avg, 2)

            total = sum(float(value) for value in numeric_values)
            if all(isinstance(value, int) for value in numeric_values):
                return int(total)
            return round(total, 2)

        return non_null[0] if non_null else None
