from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import (
    ConnectionInfo,
    ConnectionStatus,
    ConnectorBase,
    HealthStatus,
    SyncResult,
)
from app.core.exceptions import ValidationError
from app.db.models import Claim
from app.schemas.pipeline import CompiledQueryPlan


class MockClaimsConnector(ConnectorBase):
    """
    Trusted connector for local and test execution.

    Reads from immutable claim store with tenant and scope filters.
    """

    def __init__(self) -> None:
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
        return [
            {
                "entity": "claim_store",
                "fields": [
                    "tenant_id",
                    "domain",
                    "entity_type",
                    "owner_id",
                    "department_id",
                    "course_id",
                    "claim_key",
                ],
            }
        ]

    def sync(self) -> SyncResult:
        return SyncResult(
            status="complete",
            tables_discovered=1,
            tables_added=0,
            tables_removed=0,
            fields_changed=0,
            duration_ms=0,
            errors=[],
        )

    def health_check(self) -> HealthStatus:
        return HealthStatus(
            status="healthy",
            last_query_latency_ms=self._last_query_latency_ms,
            consecutive_failures=self._consecutive_failures,
            last_failure_at=self._last_failure_at,
            recommendation="No action required",
        )

    def get_connection_info(self) -> ConnectionInfo:
        return ConnectionInfo(
            connector_id="mock_claims",
            tenant_id=None,
            source_type="mock_claims",
            supports_sync=False,
            supports_live_queries=True,
        )

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
        filters = plan.filters

        stmt = select(Claim).where(
            Claim.tenant_id == str(filters["tenant_id"]),
            Claim.domain == str(filters["domain"]),
            Claim.entity_type == str(filters["entity_type"]),
            Claim.claim_key.in_(plan.select_keys),
        )

        if filters.get("owner_id"):
            stmt = stmt.where(Claim.owner_id == str(filters["owner_id"]))

        if filters.get("department_id"):
            stmt = stmt.where(Claim.department_id == str(filters["department_id"]))

        if filters.get("admin_function"):
            stmt = stmt.where(Claim.admin_function == str(filters["admin_function"]))

        course_ids = filters.get("course_ids")
        if isinstance(course_ids, list) and course_ids:
            stmt = stmt.where(Claim.course_id.in_(course_ids))

        try:
            rows = db.scalars(stmt).all()
            if not rows:
                raise ValidationError(
                    message="No records matched this scoped query", code="NO_CLAIMS_FOUND"
                )

            grouped: dict[str, list[Any]] = defaultdict(list)
            for row in rows:
                if row.value_number is not None:
                    grouped[row.claim_key].append(row.value_number)
                elif row.value_text is not None:
                    grouped[row.claim_key].append(row.value_text)
                elif row.value_json is not None:
                    grouped[row.claim_key].append(row.value_json)
                else:
                    grouped[row.claim_key].append(None)

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

    def _record_success(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures = 0
        self._last_failure_at = None

    def _record_failure(self, latency_ms: int) -> None:
        self._last_query_latency_ms = latency_ms
        self._consecutive_failures += 1
        self._last_failure_at = datetime.now(tz=UTC).isoformat()

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

        # Keep reduction deterministic and schema-agnostic: numeric aggregates sum,
        # non-numeric values pass through first non-null entry.
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


mock_claims_connector = MockClaimsConnector()
