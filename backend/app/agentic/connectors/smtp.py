from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from email.message import EmailMessage
import hashlib
import json
import time
from typing import Any

import aiosmtplib
from sqlalchemy import text

from app.agentic.models.execution_plan import ReadExecutionPlan, WriteExecutionPlan
from app.core.secret_manager import secret_manager
from app.db.models import Tenant, User
from app.db.session import SessionLocal

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


class SMTPConnector(BaseConnector):
    def __init__(self, tenant_id, config: dict[str, Any]):
        super().__init__(tenant_id=tenant_id, config=config)
        self._smtp: aiosmtplib.SMTP | None = None
        self._credentials: dict[str, Any] = {}

    async def connect(self) -> None:
        self._credentials = self._resolve_credentials()
        self._smtp = aiosmtplib.SMTP(
            hostname=str(self._credentials["host"]),
            port=int(self._credentials["port"]),
            use_tls=bool(self._credentials.get("use_tls", False)),
            timeout=10,
        )
        try:
            await self._smtp.connect()
            if not bool(self._credentials.get("use_tls", False)):
                await self._smtp.starttls()
            await self._smtp.login(
                str(self._credentials["username"]),
                str(self._credentials["password"]),
            )
            self._connected = True
        except aiosmtplib.errors.SMTPAuthenticationError as exc:
            await self.disconnect()
            raise ConnectorAuthError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            await self.disconnect()
            raise ConnectorError(str(exc)) from exc

    async def disconnect(self) -> None:
        if self._smtp is not None:
            try:
                await self._smtp.quit()
            except Exception:
                pass
        self._smtp = None
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        return {
            "email": {
                "from_alias": {"type": "string", "classification": "IDENTIFIER", "nullable": False},
                "to": {"type": "array", "classification": "PERSONAL", "nullable": False},
                "cc": {"type": "array", "classification": "PERSONAL", "nullable": True},
                "subject": {"type": "string", "classification": "GENERAL", "nullable": False},
                "body": {"type": "string", "classification": "GENERAL", "nullable": False},
            }
        }

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        del plan
        raise ConnectorError("SMTP connector does not support read operations")

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        self._validate_filter_values(plan.filters)
        assert self._smtp is not None

        payload = dict(plan.payload)
        started = time.perf_counter()
        try:
            tenant_id = str(payload.get("tenant_id") or plan.scope.tenant_id)
            from_alias = str(payload.get("from_alias") or plan.scope.user_alias or "").strip()
            if not from_alias:
                raise ConnectorError("from_alias is required")
            if str(plan.scope.user_alias or "").strip() != from_alias:
                raise MissingScopeFilter("SMTP from_alias must match scope user_alias")

            to_list = [str(item).strip() for item in (payload.get("to") or []) if str(item).strip()]
            cc_list = [str(item).strip() for item in (payload.get("cc") or []) if str(item).strip()]
            recipients = to_list + cc_list
            if not recipients:
                raise ConnectorError("At least one recipient is required")

            allowed_domains = await self._allowed_domains(tenant_id)
            self._validate_recipients(recipients=recipients, allowed_domains=allowed_domains)

            from_email = await self._resolve_from_address(alias=from_alias, tenant_id=tenant_id)

            message = EmailMessage()
            message["From"] = from_email
            message["To"] = ", ".join(to_list)
            if cc_list:
                message["Cc"] = ", ".join(cc_list)
            message["Subject"] = str(payload.get("subject") or "")
            message.set_content(str(payload.get("body") or ""))

            await self._smtp.send_message(message)

            message_hash = hashlib.sha256(message.as_bytes()).hexdigest()
            await asyncio.to_thread(
                self._log_delivery_attempt,
                tenant_id=tenant_id,
                message_hash=message_hash,
                status="SENT",
            )

            elapsed = (time.perf_counter() - started) * 1000
            details = {
                "delivery_status": "SENT",
                "message_hash": message_hash,
                "from": from_email,
                "recipient_count": len(recipients),
            }
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.action_id or plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(payload.keys()),
                row_count=1,
                execution_time_ms=elapsed,
                source_alias="smtp",
                payload={"subject": message["Subject"], "to": ",".join(recipients)},
                critical=True,
            )
            return WriteResult(
                rows_affected=1,
                generated_id=message_hash,
                execution_time_ms=elapsed,
                details=details,
            )
        except Exception as exc:  # noqa: BLE001
            message_hash = hashlib.sha256(str(payload).encode("utf-8")).hexdigest()
            await asyncio.to_thread(
                self._log_delivery_attempt,
                tenant_id=str(payload.get("tenant_id") or plan.scope.tenant_id),
                message_hash=message_hash,
                status="FAILED",
            )

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
                source_alias="smtp",
                payload=payload,
                error=str(mapped),
            )
            raise mapped from exc

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            if self._smtp is None:
                raise ConnectorError("SMTP client is not connected")
            code, _message = await self._smtp.ehlo()
            if int(code) >= 400:
                raise ConnectorError(f"SMTP EHLO failed with code {code}")

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

    async def _resolve_from_address(self, alias: str, tenant_id: str) -> str:
        return await asyncio.to_thread(self._resolve_from_address_sync, alias, tenant_id)

    def _resolve_from_address_sync(self, alias: str, tenant_id: str) -> str:
        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .filter(User.tenant_id == tenant_id)
                .filter(User.external_id == alias)
                .one_or_none()
            )
            if user is None or not user.email:
                raise ConnectorError(f"No registered email found for alias '{alias}'")
            return user.email
        finally:
            db.close()

    def _validate_recipients(self, recipients: list[str], allowed_domains: list[str]) -> None:
        allowed = {domain.strip().lower() for domain in allowed_domains if domain.strip()}
        for recipient in recipients:
            if "@" not in recipient:
                raise ConnectorError(f"Invalid recipient address '{recipient}'")
            domain = recipient.rsplit("@", 1)[1].strip().lower()
            if domain not in allowed:
                raise ConnectorError(f"Recipient {recipient} outside allowed domains")

    async def _allowed_domains(self, tenant_id: str) -> list[str]:
        return await asyncio.to_thread(self._allowed_domains_sync, tenant_id)

    def _allowed_domains_sync(self, tenant_id: str) -> list[str]:
        config_domains = self._config.get("tenant_allowed_domains")
        if isinstance(config_domains, list) and config_domains:
            return [str(item) for item in config_domains]

        db = SessionLocal()
        try:
            tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one_or_none()
            domains: list[str] = []
            if tenant is not None:
                if tenant.domain:
                    domains.append(str(tenant.domain))
                if tenant.google_workspace_domain:
                    domains.append(str(tenant.google_workspace_domain))
            return domains or ["localhost"]
        finally:
            db.close()

    def _resolve_credentials(self) -> dict[str, Any]:
        secret_key = f"smtp:{self.tenant_id}"
        fallback = json.dumps(self._config.get("smtp") or self._config)
        raw = secret_manager.get_secret(secret_key, fallback=fallback).strip()

        payload: dict[str, Any] = {}
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                payload = parsed
        except Exception:
            pass

        required = ("host", "port", "username", "password")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ConnectorAuthError(f"Missing SMTP credentials: {', '.join(missing)}")
        payload.setdefault("use_tls", True)
        return payload

    def _log_delivery_attempt(self, *, tenant_id: str, message_hash: str, status: str) -> None:
        db = SessionLocal()
        try:
            db.execute(
                text(
                    """
                    INSERT INTO smtp_delivery_log (tenant_id, message_hash, status, timestamp)
                    VALUES (:tenant_id, :message_hash, :status, :timestamp)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "message_hash": message_hash,
                    "status": status,
                    "timestamp": datetime.now(tz=UTC),
                },
            )
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

    def _map_error(self, exc: Exception) -> ConnectorError:
        if isinstance(exc, (ConnectorAuthError, ConnectorTimeoutError, ConnectorError, MissingScopeFilter)):
            return exc
        if isinstance(exc, aiosmtplib.errors.SMTPAuthenticationError):
            return ConnectorAuthError(str(exc))
        if isinstance(exc, TimeoutError):
            return ConnectorTimeoutError(str(exc))
        return ConnectorError(str(exc))
