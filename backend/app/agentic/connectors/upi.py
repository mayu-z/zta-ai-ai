from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import time
from typing import Any

import httpx

from app.agentic.models.execution_plan import ReadExecutionPlan, WriteExecutionPlan
from app.core.secret_manager import secret_manager

from .base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorError,
    ConnectorHealth,
    ConnectorTimeoutError,
    HealthStatus,
    MissingScopeFilter,
    RawResult,
    WriteResult,
)


class UPIGatewayConnector(BaseConnector):
    def __init__(self, tenant_id, config: dict[str, Any]):
        super().__init__(tenant_id=tenant_id, config=config)
        self._gateway_type = str(config.get("payment_gateway_type") or "mock").strip().lower()
        self._credentials: dict[str, str] = {}
        self._client: httpx.AsyncClient | None = None

    async def connect(self) -> None:
        self._credentials = self._resolve_credentials()
        self._client = httpx.AsyncClient(timeout=10.0)
        try:
            health = await self.health_check()
            if health.status == HealthStatus.DOWN:
                raise ConnectorError(health.error or "UPI gateway is down")
            self._connected = True
        except Exception:
            if self._client is not None:
                await self._client.aclose()
            self._client = None
            raise

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        return {
            "payment_order": {
                "payment_url": {"type": "string", "classification": "GENERAL", "nullable": False},
                "order_id": {"type": "string", "classification": "IDENTIFIER", "nullable": False},
                "expires_at": {"type": "datetime", "classification": "GENERAL", "nullable": False},
                "gateway_reference": {
                    "type": "string",
                    "classification": "IDENTIFIER",
                    "nullable": True,
                },
            }
        }

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        del plan
        raise ConnectorError("UPI connector does not support read operations")

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        self._validate_filter_values(plan.filters)

        if str(plan.operation).strip().lower() != "create_link":
            raise ConnectorError(f"UPI connector supports only create_link writes, got '{plan.operation}'")

        payload = dict(plan.payload)
        if plan.scope.user_alias != payload.get("customer_alias"):
            raise MissingScopeFilter("UPI payment scope mismatch")

        started = time.perf_counter()
        try:
            row = await self._create_order(payload)
            elapsed = (time.perf_counter() - started) * 1000
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.action_id or plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(row.keys()),
                row_count=1,
                execution_time_ms=elapsed,
                source_alias=self._gateway_type,
                payload=payload,
                critical=True,
            )
            return WriteResult(
                rows_affected=1,
                generated_id=str(row.get("order_id") or "") or None,
                execution_time_ms=elapsed,
                details=row,
            )
        except MissingScopeFilter:
            raise
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.action_id or plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(payload.keys()),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=self._gateway_type,
                payload=payload,
                error=str(mapped),
            )
            raise mapped from exc

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            if self._gateway_type == "mock":
                elapsed = (time.perf_counter() - started) * 1000
                return ConnectorHealth(
                    status=HealthStatus.HEALTHY,
                    latency_ms=elapsed,
                    last_checked_at=datetime.now(tz=UTC),
                )

            assert self._client is not None
            if self._gateway_type == "razorpay":
                base = str(self._config.get("razorpay_base_url") or "https://api.razorpay.com")
                response = await self._client.get(
                    f"{base.rstrip('/')}/v1/",
                    auth=(self._credentials.get("api_key", ""), self._credentials.get("api_secret", "")),
                )
            elif self._gateway_type == "payu":
                ping_url = str(self._config.get("payu_health_url") or "https://secure.payu.in")
                response = await self._client.get(ping_url)
            else:
                raise ConnectorError(f"Unsupported payment_gateway_type '{self._gateway_type}'")

            if response.status_code in {401, 403}:
                raise ConnectorAuthError("UPI gateway authentication failed")
            if response.status_code >= 500:
                raise ConnectorError(f"UPI gateway health failed with status {response.status_code}")

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

    async def _create_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._gateway_type == "mock":
            order_id = str(payload.get("order_id") or "ORDER-MOCK")
            expiry = int(payload.get("expiry_seconds") or 1800)
            expires_at = datetime.now(tz=UTC) + timedelta(seconds=expiry)
            return {
                "payment_url": f"https://mock-upi.local/pay/{order_id}",
                "order_id": order_id,
                "expires_at": expires_at.isoformat(),
                "gateway_reference": f"mock-{order_id}",
            }

        if self._gateway_type == "razorpay":
            return await self._build_razorpay_order(payload)
        if self._gateway_type == "payu":
            return await self._build_payu_order(payload)
        raise ConnectorError(f"Unsupported payment_gateway_type '{self._gateway_type}'")

    async def _build_razorpay_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        base = str(self._config.get("razorpay_base_url") or "https://api.razorpay.com")
        request_payload = {
            "amount": int(payload["amount_paise"]),
            "currency": str(payload.get("currency") or "INR"),
            "receipt": str(payload["order_id"]),
            "notes": {
                "description": payload.get("description", ""),
                "customer_alias": payload.get("customer_alias", ""),
            },
        }
        response = await self._client.post(
            f"{base.rstrip('/')}/v1/orders",
            json=request_payload,
            auth=(self._credentials.get("api_key", ""), self._credentials.get("api_secret", "")),
        )
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Razorpay authentication failed")
        if response.status_code >= 400:
            raise ConnectorError(f"Razorpay order creation failed with status {response.status_code}")

        body = response.json()
        gateway_ref = str(body.get("id") or "")
        order_id = str(payload["order_id"])
        expiry = int(payload.get("expiry_seconds") or 1800)
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=expiry)
        return {
            "payment_url": f"https://rzp.io/i/{gateway_ref or order_id}",
            "order_id": order_id,
            "expires_at": expires_at.isoformat(),
            "gateway_reference": gateway_ref or order_id,
        }

    async def _build_payu_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self._client is not None
        url = str(
            self._config.get("payu_order_url")
            or "https://secure.payu.in/merchant/postservice.php"
        )

        request_payload = {
            "key": self._credentials.get("merchant_key", ""),
            "txnid": str(payload["order_id"]),
            "amount": float(payload["amount_paise"]) / 100,
            "productinfo": str(payload.get("description") or "fee_payment"),
            "firstname": str(payload.get("customer_alias") or "user"),
            "email": "no-reply@local.invalid",
        }
        response = await self._client.post(url, data=request_payload)
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("PayU authentication failed")
        if response.status_code >= 400:
            raise ConnectorError(f"PayU order creation failed with status {response.status_code}")

        order_id = str(payload["order_id"])
        expiry = int(payload.get("expiry_seconds") or 1800)
        expires_at = datetime.now(tz=UTC) + timedelta(seconds=expiry)
        return {
            "payment_url": f"https://secure.payu.in/pay/{order_id}",
            "order_id": order_id,
            "expires_at": expires_at.isoformat(),
            "gateway_reference": order_id,
        }

    def _resolve_credentials(self) -> dict[str, str]:
        if self._gateway_type == "mock":
            return {}

        secret_key = f"payment_gateway:{self.tenant_id}"
        fallback = json.dumps(self._config.get("gateway_credentials") or {})
        raw = secret_manager.get_secret(secret_key, fallback=fallback).strip()

        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            pass

        if self._gateway_type == "razorpay":
            key = str(payload.get("api_key") or "").strip()
            secret = str(payload.get("api_secret") or "").strip()
            if not key or not secret:
                raise ConnectorAuthError("Missing Razorpay credentials")
            return {"api_key": key, "api_secret": secret}

        if self._gateway_type == "payu":
            key = str(payload.get("merchant_key") or "").strip()
            salt = str(payload.get("merchant_salt") or "").strip()
            if not key or not salt:
                raise ConnectorAuthError("Missing PayU credentials")
            return {"merchant_key": key, "merchant_salt": salt}

        raise ConnectorError(f"Unsupported payment_gateway_type '{self._gateway_type}'")

    def _map_error(self, exc: Exception) -> ConnectorError:
        if isinstance(exc, (ConnectorAuthError, ConnectorTimeoutError, ConnectorError)):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return ConnectorTimeoutError(str(exc))
        if isinstance(exc, httpx.HTTPError):
            return ConnectorError(str(exc))
        return ConnectorError(str(exc))
