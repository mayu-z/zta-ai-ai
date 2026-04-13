from __future__ import annotations

from datetime import UTC, datetime
import json
import time
from typing import Any

import httpx

from app.agentic.models.execution_plan import FilterOperator, QueryFilter, ReadExecutionPlan, WriteExecutionPlan
from app.core.secret_manager import secret_manager

from .base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorError,
    ConnectorHealth,
    ConnectorTimeoutError,
    HealthStatus,
    MissingScopeFilter,
    QueryInjectionAttempt,
    RawResult,
    WriteResult,
)


OPERATOR_MAP = {
    FilterOperator.EQ: "=",
    FilterOperator.NEQ: "!=",
    FilterOperator.GT: ">",
    FilterOperator.GTE: ">=",
    FilterOperator.LT: "<",
    FilterOperator.LTE: "<=",
    FilterOperator.LIKE: "like",
    FilterOperator.IN: "in",
    FilterOperator.IS_NULL: "is",
}


class ERPNextConnector(BaseConnector):
    def __init__(self, tenant_id, config: dict[str, Any]):
        super().__init__(tenant_id=tenant_id, config=config)
        self._client: httpx.AsyncClient | None = None
        self._api_key: str = ""
        self._api_secret: str = ""
        self._base_url = str(config.get("erp_base_url") or config.get("base_url") or "").rstrip("/")
        self._verify_tls = bool(config.get("verify_tls", True))
        self._tenant_company = str(config.get("tenant_company_name") or "").strip()

    async def connect(self) -> None:
        creds = self._resolve_credentials()
        self._api_key = creds["api_key"]
        self._api_secret = creds["api_secret"]

        if not self._base_url:
            raise ConnectorError("ERPNext base URL is required")

        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"token {self._api_key}:{self._api_secret}"},
            timeout=10.0,
            verify=self._verify_tls,
        )
        try:
            await self._ping()
            self._connected = True
        except Exception as exc:  # noqa: BLE001
            await self.disconnect()
            raise self._map_http_error(exc) from exc

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        self._ensure_connected()
        assert self._client is not None

        entity_mappings = self._entity_mappings()
        discovered: dict[str, Any] = {}
        for entity, doctype in entity_mappings.items():
            resp = await self._client.get(f"/api/resource/DocType/{doctype}")
            if resp.status_code >= 400:
                continue
            payload = resp.json()
            data = payload.get("data") if isinstance(payload, dict) else None
            fields = data.get("fields") if isinstance(data, dict) else []

            discovered[entity] = {}
            if isinstance(fields, list):
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    field_name = str(field.get("fieldname") or "").strip()
                    if not field_name:
                        continue
                    field_type = str(field.get("fieldtype") or "Data")
                    discovered[entity][field_name] = {
                        "type": field_type,
                        "classification": self._classify_field(field_name, field_type),
                        "nullable": True,
                    }
        return discovered

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_filter_values(plan.filters)
        assert self._client is not None

        started = time.perf_counter()
        doctype = self._get_doctype(plan.entity)
        filters = self._translate_filters(plan.filters)
        filters.append(["tenant_id", "=", plan.scope.tenant_id])
        if self._tenant_company:
            filters.append(["company", "=", self._tenant_company])

        params: dict[str, Any] = {
            "filters": json.dumps(filters),
            "limit_page_length": str(min(max(plan.limit, 1), 1000)),
            "limit_start": str(max(plan.offset, 0)),
        }
        if plan.fields:
            params["fields"] = json.dumps(plan.fields)

        try:
            resp = await self._client.get(f"/api/resource/{doctype}", params=params)
            if resp.status_code == 401:
                raise ConnectorAuthError("ERPNext authentication failed")
            if resp.status_code >= 400:
                raise ConnectorError(f"ERPNext query failed with status {resp.status_code}")

            payload = resp.json()
            rows = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(rows, list):
                rows = []

            elapsed = (time.perf_counter() - started) * 1000
            mapped_rows = [dict(row) for row in rows if isinstance(row, dict)]
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(mapped_rows[0].keys()) if mapped_rows else list(plan.fields),
                row_count=len(mapped_rows),
                execution_time_ms=elapsed,
                source_alias=doctype,
            )
            return RawResult(
                rows=mapped_rows,
                row_count=len(mapped_rows),
                execution_time_ms=elapsed,
                source_schema=doctype,
            )
        except (MissingScopeFilter, QueryInjectionAttempt):
            raise
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_http_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(plan.fields),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=doctype,
                error=str(mapped),
            )
            raise mapped from exc

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_filter_values(plan.filters)
        assert self._client is not None

        started = time.perf_counter()
        doctype = self._get_doctype(plan.entity)
        operation = plan.operation.upper()
        payload = dict(plan.payload)
        payload.setdefault("tenant_id", plan.scope.tenant_id)
        if self._tenant_company:
            payload.setdefault("company", self._tenant_company)

        try:
            if operation == "INSERT":
                resp = await self._client.post(f"/api/resource/{doctype}", json=payload)
            elif operation == "UPDATE":
                name = str(payload.pop("name", "")).strip()
                if not name:
                    raise ConnectorError("ERPNext update requires payload.name")
                resp = await self._client.put(f"/api/resource/{doctype}/{name}", json=payload)
            elif operation == "DELETE":
                name = str(payload.get("name", "")).strip()
                if not name:
                    raise ConnectorError("ERPNext delete requires payload.name")
                resp = await self._client.delete(f"/api/resource/{doctype}/{name}")
            else:
                raise ConnectorError(f"Unsupported ERPNext write operation '{plan.operation}'")

            if resp.status_code == 401:
                raise ConnectorAuthError("ERPNext authentication failed")
            if resp.status_code >= 400:
                raise ConnectorError(f"ERPNext write failed with status {resp.status_code}")

            body = resp.json() if resp.content else {}
            generated_id = None
            if isinstance(body, dict):
                data = body.get("data")
                if isinstance(data, dict):
                    generated_id = str(data.get("name") or "") or None

            elapsed = (time.perf_counter() - started) * 1000
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(plan.payload.keys()),
                row_count=1,
                execution_time_ms=elapsed,
                source_alias=doctype,
                payload=plan.payload,
            )
            return WriteResult(rows_affected=1, generated_id=generated_id, execution_time_ms=elapsed)
        except (MissingScopeFilter, QueryInjectionAttempt):
            raise
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_http_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(plan.payload.keys()),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=doctype,
                payload=plan.payload,
                error=str(mapped),
            )
            raise mapped from exc

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            await self._ping()
            elapsed = (time.perf_counter() - started) * 1000
            return ConnectorHealth(
                status=HealthStatus.HEALTHY,
                latency_ms=elapsed,
                last_checked_at=datetime.now(tz=UTC),
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            return ConnectorHealth(
                status=HealthStatus.DOWN,
                latency_ms=elapsed,
                error=str(exc),
                last_checked_at=datetime.now(tz=UTC),
            )

    def _translate_filters(self, filters: list[QueryFilter]) -> list[list[Any]]:
        translated: list[list[Any]] = []
        for item in filters:
            op = OPERATOR_MAP.get(item.operator)
            if op is None:
                raise ConnectorError(f"Unsupported ERPNext operator '{item.operator}'")
            value = item.value
            if item.operator == FilterOperator.IS_NULL:
                value = "null" if bool(item.value) else "not null"
            translated.append([item.field, op, value])
        return translated

    def _get_doctype(self, entity: str) -> str:
        entity_map = self._entity_mappings()
        mapped = entity_map.get(entity)
        return str(mapped or entity)

    async def _ping(self) -> None:
        if self._client is None:
            raise ConnectorError("ERPNext client not connected")
        try:
            resp = await self._client.get("/api/method/frappe.ping")
            if resp.status_code == 401:
                raise ConnectorAuthError("ERPNext authentication failed")
            resp.raise_for_status()
            payload = resp.json()
            if not isinstance(payload, dict):
                raise ConnectorError("Invalid ERPNext ping payload")
        except Exception as exc:  # noqa: BLE001
            raise self._map_http_error(exc) from exc

    def _resolve_credentials(self) -> dict[str, str]:
        secret_key = f"erpnext:{self.tenant_id}"
        fallback_raw = json.dumps(
            {
                "api_key": self._config.get("api_key", ""),
                "api_secret": self._config.get("api_secret", ""),
            }
        )
        raw = secret_manager.get_secret(secret_key, fallback=fallback_raw).strip()
        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            if ":" in raw:
                key, secret = raw.split(":", 1)
                payload = {"api_key": key, "api_secret": secret}

        api_key = str(payload.get("api_key") or "").strip()
        api_secret = str(payload.get("api_secret") or "").strip()
        if not api_key or not api_secret:
            raise ConnectorAuthError("ERPNext credentials are missing in secrets manager")
        return {"api_key": api_key, "api_secret": api_secret}

    def _entity_mappings(self) -> dict[str, str]:
        mappings = self._config.get("entity_mappings")
        if isinstance(mappings, dict):
            return {str(k): str(v) for k, v in mappings.items()}
        fallback = self._config.get("entity_mapping")
        if isinstance(fallback, dict):
            return {str(k): str(v) for k, v in fallback.items()}
        return {
            "fees": "Fees",
            "student": "Student",
            "attendance": "Student Attendance",
            "results": "Exam Result",
        }

    def _classify_field(self, field_name: str, field_type: str) -> str:
        name = field_name.lower()
        typ = field_type.lower()
        if "biometric" in name:
            return "BIOMETRIC"
        if any(token in name for token in ("medical", "health", "phi")):
            return "PHI"
        if any(token in name for token in ("salary", "ssn", "aadhaar", "pan")):
            return "SENSITIVE"
        if typ in {"email", "phone", "mobile"} or "name" in name:
            return "PERSONAL"
        if name.endswith("_id"):
            return "IDENTIFIER"
        return "GENERAL"

    def _map_http_error(self, exc: Exception) -> ConnectorError:
        if isinstance(exc, (ConnectorAuthError, ConnectorTimeoutError, ConnectorError)):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return ConnectorTimeoutError(str(exc))
        if isinstance(exc, httpx.HTTPStatusError):
            status = exc.response.status_code
            if status == 401:
                return ConnectorAuthError("ERPNext authentication failed")
            return ConnectorError(f"ERPNext HTTP error {status}")
        return ConnectorError(str(exc))
