from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
import json
import time
from typing import Any

import httpx

from app.agentic.models.execution_plan import ReadExecutionPlan, WriteExecutionPlan
from app.core.secret_manager import secret_manager
from app.db.models import User
from app.db.session import SessionLocal

from .base import (
    BaseConnector,
    ConnectorAuthError,
    ConnectorError,
    ConnectorHealth,
    ConnectorTimeoutError,
    HealthStatus,
    RawResult,
    WriteResult,
)


class _CalendarBaseConnector(BaseConnector):
    provider_name = "calendar"
    secret_prefix = "calendar"

    def __init__(self, tenant_id, config: dict[str, Any]):
        super().__init__(tenant_id=tenant_id, config=config)
        self._client: httpx.AsyncClient | None = None
        self._token: str = ""
        self._base_url = str(config.get("base_url") or "").rstrip("/")

    async def connect(self) -> None:
        self._token = self._resolve_token()
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers={"Authorization": f"Bearer {self._token}"},
        )
        health = await self.health_check()
        if health.status == HealthStatus.DOWN:
            await self.disconnect()
            raise ConnectorError(health.error or f"{self.provider_name} connector unavailable")
        self._connected = True

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
        self._client = None
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        return {
            "calendar": {
                "user_alias": {"type": "string", "classification": "IDENTIFIER", "nullable": False},
                "busy_start": {"type": "datetime", "classification": "GENERAL", "nullable": False},
                "busy_end": {"type": "datetime", "classification": "GENERAL", "nullable": False},
            }
        }

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        self._validate_filter_values(plan.filters)

        operation = str(plan.operation or "free_busy").strip().lower()
        if operation != "free_busy":
            raise ConnectorError("Calendar connector execute supports only free_busy")

        payload = dict(plan.payload)
        user_aliases = [str(item) for item in payload.get("user_aliases", []) if str(item).strip()]
        start = str(payload.get("start") or "").strip()
        end = str(payload.get("end") or "").strip()
        if not user_aliases or not start or not end:
            raise ConnectorError("Calendar free_busy payload requires user_aliases, start, and end")

        started = time.perf_counter()
        try:
            rows = await self._fetch_free_busy(user_aliases=user_aliases, start=start, end=end)
            elapsed = (time.perf_counter() - started) * 1000
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.action_id or plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=["user_alias", "busy_start", "busy_end"],
                row_count=len(rows),
                execution_time_ms=elapsed,
                source_alias=self.provider_name,
            )
            return RawResult(
                rows=rows,
                row_count=len(rows),
                execution_time_ms=elapsed,
                source_schema=self.provider_name,
            )
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_READ",
                action_id=plan.action_id or plan.plan_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=["user_alias", "busy_start", "busy_end"],
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=self.provider_name,
                error=str(mapped),
            )
            raise mapped from exc

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._ensure_connected()
        self._validate_scope(plan.scope)
        self._validate_scope_filters(plan.filters, plan.scope, plan.scope_filters_required)
        self._validate_filter_values(plan.filters)

        started = time.perf_counter()
        try:
            payload = dict(plan.payload)
            event_id = await self._create_event(payload)
            elapsed = (time.perf_counter() - started) * 1000
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.action_id or plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="SUCCESS",
                fields=list(payload.keys()),
                row_count=1,
                execution_time_ms=elapsed,
                source_alias=self.provider_name,
                payload=payload,
                critical=True,
            )
            return WriteResult(rows_affected=1, generated_id=event_id, execution_time_ms=elapsed)
        except Exception as exc:  # noqa: BLE001
            elapsed = (time.perf_counter() - started) * 1000
            mapped = self._map_error(exc)
            await self._audit_execution(
                event_type="CONNECTOR_WRITE",
                action_id=plan.action_id or plan.allowed_by_action_id,
                user_alias=plan.scope.user_alias or "unknown",
                status="FAILED",
                fields=list(plan.payload.keys()),
                row_count=0,
                execution_time_ms=elapsed,
                source_alias=self.provider_name,
                payload=plan.payload,
                error=str(mapped),
            )
            raise mapped from exc

    def _resolve_token(self) -> str:
        secret_key = f"{self.secret_prefix}:{self.tenant_id}"
        fallback = str(self._config.get("access_token") or "")
        token = secret_manager.get_secret(secret_key, fallback=fallback).strip()
        if not token:
            raise ConnectorAuthError(f"Missing {self.provider_name} access token")
        return token

    async def _resolve_user_address(self, alias: str) -> str:
        return await asyncio.to_thread(self._resolve_user_address_sync, alias)

    def _resolve_user_address_sync(self, alias: str) -> str:
        db = SessionLocal()
        try:
            user = (
                db.query(User)
                .filter(User.tenant_id == str(self.tenant_id))
                .filter(User.external_id == alias)
                .one_or_none()
            )
            if user is None or not user.email:
                raise ConnectorError(f"No calendar identity found for alias '{alias}'")
            return str(user.email)
        finally:
            db.close()

    def _map_error(self, exc: Exception) -> ConnectorError:
        if isinstance(exc, (ConnectorAuthError, ConnectorTimeoutError, ConnectorError)):
            return exc
        if isinstance(exc, httpx.TimeoutException):
            return ConnectorTimeoutError(str(exc))
        if isinstance(exc, httpx.HTTPStatusError):
            if exc.response.status_code in {401, 403}:
                return ConnectorAuthError(str(exc))
            return ConnectorError(str(exc))
        if isinstance(exc, httpx.HTTPError):
            return ConnectorError(str(exc))
        return ConnectorError(str(exc))

    async def _fetch_free_busy(self, *, user_aliases: list[str], start: str, end: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    async def _create_event(self, payload: dict[str, Any]) -> str:
        raise NotImplementedError


class GoogleCalendarConnector(_CalendarBaseConnector):
    provider_name = "calendar_google"
    secret_prefix = "calendar_google"

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            assert self._client is not None
            response = await self._client.get(
                "https://www.googleapis.com/calendar/v3/users/me/calendarList"
            )
            if response.status_code in {401, 403}:
                raise ConnectorAuthError("Google Calendar authentication failed")
            response.raise_for_status()
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

    async def _fetch_free_busy(self, *, user_aliases: list[str], start: str, end: str) -> list[dict[str, Any]]:
        assert self._client is not None
        aliases_to_email = {
            alias: await self._resolve_user_address(alias)
            for alias in user_aliases
        }
        payload = {
            "timeMin": start,
            "timeMax": end,
            "items": [{"id": email} for email in aliases_to_email.values()],
        }
        response = await self._client.post(
            "https://www.googleapis.com/calendar/v3/freeBusy",
            json=payload,
        )
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Google Calendar authentication failed")
        response.raise_for_status()

        data = response.json()
        calendars = data.get("calendars", {}) if isinstance(data, dict) else {}

        rows: list[dict[str, Any]] = []
        for alias, email in aliases_to_email.items():
            busy_blocks = calendars.get(email, {}).get("busy", []) if isinstance(calendars, dict) else []
            for block in busy_blocks:
                rows.append(
                    {
                        "user_alias": alias,
                        "busy_start": block.get("start"),
                        "busy_end": block.get("end"),
                    }
                )
        return rows

    async def _create_event(self, payload: dict[str, Any]) -> str:
        assert self._client is not None
        attendee_aliases = [str(item) for item in payload.get("attendee_aliases", [])]
        attendees = [{"email": await self._resolve_user_address(alias)} for alias in attendee_aliases]

        body = {
            "summary": str(payload.get("title") or "Scheduled Meeting"),
            "start": {"dateTime": str(payload.get("start"))},
            "end": {"dateTime": str(payload.get("end"))},
            "attendees": attendees,
        }
        if payload.get("location"):
            body["location"] = str(payload["location"])

        response = await self._client.post(
            "https://www.googleapis.com/calendar/v3/calendars/primary/events",
            json=body,
        )
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Google Calendar authentication failed")
        response.raise_for_status()
        result = response.json()
        return str(result.get("id") or "")


class MicrosoftCalendarConnector(_CalendarBaseConnector):
    provider_name = "calendar_ms"
    secret_prefix = "calendar_ms"

    async def health_check(self) -> ConnectorHealth:
        started = time.perf_counter()
        try:
            assert self._client is not None
            response = await self._client.get("https://graph.microsoft.com/v1.0/me")
            if response.status_code in {401, 403}:
                raise ConnectorAuthError("Microsoft Calendar authentication failed")
            response.raise_for_status()
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

    async def _fetch_free_busy(self, *, user_aliases: list[str], start: str, end: str) -> list[dict[str, Any]]:
        assert self._client is not None
        rows: list[dict[str, Any]] = []
        for alias in user_aliases:
            email = await self._resolve_user_address(alias)
            response = await self._client.get(
                f"https://graph.microsoft.com/v1.0/users/{email}/calendarView",
                params={
                    "startDateTime": start,
                    "endDateTime": end,
                    "$select": "start,end",
                },
            )
            if response.status_code in {401, 403}:
                raise ConnectorAuthError("Microsoft Calendar authentication failed")
            response.raise_for_status()
            payload = response.json()
            events = payload.get("value", []) if isinstance(payload, dict) else []
            for event in events:
                start_obj = event.get("start", {}) if isinstance(event, dict) else {}
                end_obj = event.get("end", {}) if isinstance(event, dict) else {}
                rows.append(
                    {
                        "user_alias": alias,
                        "busy_start": start_obj.get("dateTime"),
                        "busy_end": end_obj.get("dateTime"),
                    }
                )
        return rows

    async def _create_event(self, payload: dict[str, Any]) -> str:
        assert self._client is not None
        attendee_aliases = [str(item) for item in payload.get("attendee_aliases", [])]
        attendees = [
            {
                "emailAddress": {"address": await self._resolve_user_address(alias)},
                "type": "required",
            }
            for alias in attendee_aliases
        ]

        body = {
            "subject": str(payload.get("title") or "Scheduled Meeting"),
            "start": {"dateTime": str(payload.get("start")), "timeZone": "UTC"},
            "end": {"dateTime": str(payload.get("end")), "timeZone": "UTC"},
            "attendees": attendees,
        }
        if payload.get("location"):
            body["location"] = {"displayName": str(payload["location"])}

        response = await self._client.post("https://graph.microsoft.com/v1.0/me/events", json=body)
        if response.status_code in {401, 403}:
            raise ConnectorAuthError("Microsoft Calendar authentication failed")
        response.raise_for_status()
        result = response.json()
        return str(result.get("id") or "")


class MockCalendarConnector(BaseConnector):
    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def discover_schema(self) -> dict[str, Any]:
        return {
            "calendar": {
                "user_alias": {"type": "string", "classification": "IDENTIFIER", "nullable": False},
                "busy_start": {"type": "datetime", "classification": "GENERAL", "nullable": False},
                "busy_end": {"type": "datetime", "classification": "GENERAL", "nullable": False},
            }
        }

    async def execute(self, plan: ReadExecutionPlan) -> RawResult:
        self._validate_scope(plan.scope)
        payload = dict(plan.payload)
        user_aliases = [str(item) for item in payload.get("user_aliases", []) if str(item).strip()]
        start = datetime.fromisoformat(str(payload.get("start")).replace("Z", "+00:00"))

        rows = []
        for index, alias in enumerate(user_aliases):
            busy_start = start + timedelta(minutes=30 * index)
            busy_end = busy_start + timedelta(minutes=30)
            rows.append(
                {
                    "user_alias": alias,
                    "busy_start": busy_start.isoformat(),
                    "busy_end": busy_end.isoformat(),
                }
            )

        return RawResult(rows=rows, row_count=len(rows), execution_time_ms=1.0, source_schema="calendar_mock")

    async def write(self, plan: WriteExecutionPlan) -> WriteResult:
        self._validate_scope(plan.scope)
        return WriteResult(rows_affected=1, generated_id="mock-event-id", execution_time_ms=1.0)

    async def health_check(self) -> ConnectorHealth:
        return ConnectorHealth(
            status=HealthStatus.HEALTHY,
            latency_ms=1.0,
            last_checked_at=datetime.now(tz=UTC),
        )
