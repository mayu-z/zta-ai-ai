from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors.base import ConnectorBase
from app.core.exceptions import ValidationError
from app.db.models import Claim
from app.schemas.pipeline import CompiledQueryPlan


class MockClaimsConnector(ConnectorBase):
    """
    Trusted connector for local and test execution.

    Reads from immutable claim store with tenant and scope filters.
    """

    def connect(self) -> None:
        return None

    def discover_schema(self) -> list[dict[str, Any]]:
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

    def sync(self) -> None:
        return None

    def execute_query(self, db: Session, plan: CompiledQueryPlan) -> dict[str, Any]:
        filters = plan.filters

        stmt = select(Claim).where(
            Claim.tenant_id == str(filters["tenant_id"]),
            Claim.domain == str(filters["domain"]),
            Claim.entity_type == str(filters["entity_type"]),
            Claim.claim_key.in_(plan.select_claim_keys),
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

        rows = db.scalars(stmt).all()
        if not rows:
            raise ValidationError(
                message="No claims matched this scoped query", code="NO_CLAIMS_FOUND"
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

        for expected_key in plan.select_claim_keys:
            result.setdefault(expected_key, None)

        return result

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

        average_keys = {
            "function_metric",
            "attendance_percentage",
            "avg_attendance",
            "gpa",
            "pass_rate",
        }

        # Keep reduction deterministic and schema-agnostic: numeric aggregates sum,
        # non-numeric values pass through first non-null entry.
        if non_null and len(numeric_values) == len(non_null):
            if claim_key in average_keys:
                avg = sum(float(value) for value in numeric_values) / len(numeric_values)
                return round(avg, 2)

            total = sum(float(value) for value in numeric_values)
            if all(isinstance(value, int) for value in numeric_values):
                return int(total)
            return round(total, 2)

        return non_null[0] if non_null else None


mock_claims_connector = MockClaimsConnector()
