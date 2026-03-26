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
                "fields": ["tenant_id", "domain", "entity_type", "owner_id", "department_id", "course_id", "claim_key"],
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
            raise ValidationError(message="No claims matched this scoped query", code="NO_CLAIMS_FOUND")

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
            if plan.requires_aggregate and values:
                if all(isinstance(v, (int, float)) for v in values if v is not None):
                    if claim_key.endswith("count") or claim_key.startswith("count_"):
                        result[claim_key] = int(sum(v for v in values if isinstance(v, (int, float))))
                    else:
                        numeric_values = [float(v) for v in values if isinstance(v, (int, float))]
                        result[claim_key] = round(sum(numeric_values) / max(len(numeric_values), 1), 2)
                else:
                    result[claim_key] = values[0]
            else:
                result[claim_key] = values[0]

        for expected_key in plan.select_claim_keys:
            result.setdefault(expected_key, None)

        return result


mock_claims_connector = MockClaimsConnector()
