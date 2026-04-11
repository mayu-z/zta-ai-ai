from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ValidationError
from app.db.models import ComplianceAttestation
from app.schemas.pipeline import ScopeContext
from app.services.action_orchestrator import action_orchestrator_service
from app.services.compliance_operations import (
    COMPLIANCE_ACTION_IDS,
    compliance_operations_service,
)


DEFAULT_WINDOW_DAYS = 30
SUPPORTED_FRAMEWORKS = {
    "HIPAA",
    "GDPR",
    "DPDP",
    "SOC2",
    "ISO27001",
}
FRAMEWORK_ALIASES = {
    "HIPAA": "HIPAA",
    "GDPR": "GDPR",
    "DPDP": "DPDP",
    "SOC2": "SOC2",
    "SOCII": "SOC2",
    "SOC2TYPEII": "SOC2",
    "ISO27001": "ISO27001",
    "ISO27K": "ISO27001",
}


class ComplianceAttestationService:
    def create_attestation(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        framework: str,
        from_at: datetime | None,
        to_at: datetime | None,
        max_items: int,
        statement: str | None,
    ) -> dict[str, object]:
        normalized_framework = self._normalize_framework(framework)
        window_from, window_to = self._normalize_window(from_at=from_at, to_at=to_at)

        summary = compliance_operations_service.get_summary(
            scope=scope,
            db=db,
            from_at=window_from,
            to_at=window_to,
            limit=max_items,
        )

        action_records = action_orchestrator_service.list_executions_for_tenant(
            db=db,
            tenant_id=scope.tenant_id,
            action_ids=COMPLIANCE_ACTION_IDS,
            from_at=window_from,
            to_at=window_to,
            limit=max_items,
        )

        generated_at = datetime.now(tz=UTC)
        signed_payload = {
            "tenant_id": scope.tenant_id,
            "framework": normalized_framework,
            "period": {
                "from": window_from.isoformat(),
                "to": window_to.isoformat(),
            },
            "requested_by": scope.user_id,
            "generated_at": generated_at.isoformat(),
            "statement": self._build_statement(
                framework=normalized_framework,
                window_from=window_from,
                window_to=window_to,
                statement=statement,
            ),
            "summary": summary,
            "evidence": {
                "action_count": len(action_records),
                "action_execution_ids": [
                    str(record.get("execution_id"))
                    for record in action_records
                    if record.get("execution_id")
                ],
                "audit": summary.get("audit", {}),
            },
        }

        canonical_payload = self._canonicalize_payload(signed_payload)
        payload_digest = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
        signature = self._sign_payload(canonical_payload)

        row = ComplianceAttestation(
            tenant_id=scope.tenant_id,
            framework=normalized_framework,
            period_start=window_from,
            period_end=window_to,
            requested_by=scope.user_id,
            payload=signed_payload,
            payload_digest=payload_digest,
            signature_algorithm="HMAC-SHA256",
            signature=signature,
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return self._serialize_attestation(row, include_payload=True)

    def list_attestations(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        framework: str | None,
        from_at: datetime | None,
        to_at: datetime | None,
        limit: int,
    ) -> dict[str, object]:
        filters = [ComplianceAttestation.tenant_id == scope.tenant_id]

        normalized_framework = None
        if framework is not None:
            normalized_framework = self._normalize_framework(framework)
            filters.append(ComplianceAttestation.framework == normalized_framework)

        normalized_from = self._normalize_datetime(from_at)
        normalized_to = self._normalize_datetime(to_at)
        if normalized_from and normalized_to and normalized_from > normalized_to:
            normalized_from, normalized_to = normalized_to, normalized_from

        if normalized_from is not None:
            filters.append(ComplianceAttestation.period_end >= normalized_from)
        if normalized_to is not None:
            filters.append(ComplianceAttestation.period_start <= normalized_to)

        rows = db.scalars(
            select(ComplianceAttestation)
            .where(*filters)
            .order_by(ComplianceAttestation.created_at.desc())
            .limit(limit)
        ).all()

        return {
            "items": [self._serialize_attestation(row, include_payload=False) for row in rows],
            "count": len(rows),
            "framework": normalized_framework,
        }

    @staticmethod
    def _build_statement(
        *,
        framework: str,
        window_from: datetime,
        window_to: datetime,
        statement: str | None,
    ) -> str:
        if statement is not None and statement.strip():
            return statement.strip()
        return (
            f"Compliance attestation for {framework} covering "
            f"{window_from.date().isoformat()} to {window_to.date().isoformat()}."
        )

    @staticmethod
    def _serialize_attestation(
        row: ComplianceAttestation,
        *,
        include_payload: bool,
    ) -> dict[str, object]:
        item: dict[str, object] = {
            "attestation_id": row.attestation_id,
            "framework": row.framework,
            "period": {
                "from": row.period_start.isoformat(),
                "to": row.period_end.isoformat(),
            },
            "requested_by": row.requested_by,
            "signature_algorithm": row.signature_algorithm,
            "signature": row.signature,
            "payload_digest": row.payload_digest,
            "created_at": row.created_at.isoformat(),
        }
        if include_payload:
            item["signed_payload"] = dict(row.payload or {})
        return item

    @staticmethod
    def _canonicalize_payload(payload: dict[str, object]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def _normalize_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def _normalize_window(
        self,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
    ) -> tuple[datetime, datetime]:
        normalized_to = self._normalize_datetime(to_at) or datetime.now(tz=UTC)
        normalized_from = self._normalize_datetime(from_at) or (
            normalized_to - timedelta(days=DEFAULT_WINDOW_DAYS)
        )

        if normalized_from > normalized_to:
            normalized_from, normalized_to = normalized_to, normalized_from
        return normalized_from, normalized_to

    @staticmethod
    def _normalize_framework(value: str) -> str:
        normalized = "".join(ch for ch in value.strip().upper() if ch.isalnum())
        if not normalized:
            raise ValidationError(
                message="framework is required",
                code="COMPLIANCE_FRAMEWORK_REQUIRED",
            )

        canonical = FRAMEWORK_ALIASES.get(normalized, normalized)
        if canonical not in SUPPORTED_FRAMEWORKS:
            raise ValidationError(
                message=(
                    "framework must be one of HIPAA, GDPR, DPDP, SOC2, ISO27001"
                ),
                code="COMPLIANCE_FRAMEWORK_NOT_SUPPORTED",
            )
        return canonical

    @staticmethod
    def _sign_payload(canonical_payload: str) -> str:
        settings = get_settings()
        key = settings.jwt_secret_key.encode("utf-8")
        message = canonical_payload.encode("utf-8")
        return hmac.new(key, message, hashlib.sha256).hexdigest()


compliance_attestation_service = ComplianceAttestationService()
