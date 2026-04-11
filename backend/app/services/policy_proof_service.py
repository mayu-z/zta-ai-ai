from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from app.db.models import PolicyProofArtifact
from app.schemas.pipeline import CompiledQueryPlan, PolicyDecision, ScopeContext


class PolicyProofService:
    def _digest(self, payload: dict[str, object]) -> str:
        canonical_payload = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        return hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()

    def persist_query_proofs(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        query_text: str,
        intent_hash: str,
        pipeline_id: str,
        proofs: list[dict[str, object]],
    ) -> list[str]:
        proof_ids: list[str] = []

        for entry in proofs:
            compiled_query = entry["compiled_query"]
            if not isinstance(compiled_query, CompiledQueryPlan):
                raise TypeError("compiled_query must be a CompiledQueryPlan")

            decision = entry.get("policy_decision")
            if not isinstance(decision, PolicyDecision):
                decision = PolicyDecision(allowed=True)

            masked_fields = [str(field) for field in list(entry.get("masked_fields", []))]
            now = datetime.now(tz=UTC)
            sensitive_domain = compiled_query.domain in set(scope.sensitive_domains or [])

            scope_snapshot = {
                "persona_type": scope.persona_type,
                "role_key": scope.role_key,
                "allowed_domains": list(scope.allowed_domains or []),
                "row_scope_mode": scope.row_scope_mode,
                "row_scope_filters": dict(scope.row_scope_filters or {}),
                "aggregate_only": scope.aggregate_only,
                "masked_fields": list(scope.masked_fields or []),
                "session_ip": scope.session_ip,
                "device_trusted": scope.device_trusted,
                "mfa_verified": scope.mfa_verified,
            }
            policy_snapshot = {
                "allowed": decision.allowed,
                "reason": decision.reason,
                "sensitive_domain": sensitive_domain,
                "require_business_hours_for_sensitive": scope.require_business_hours_for_sensitive,
                "require_trusted_device_for_sensitive": scope.require_trusted_device_for_sensitive,
                "require_mfa_for_sensitive": scope.require_mfa_for_sensitive,
                "business_hours_start": scope.business_hours_start,
                "business_hours_end": scope.business_hours_end,
            }
            reasoning = {
                "domain_allowed": compiled_query.domain in set(scope.allowed_domains or []),
                "masking_applied": bool(masked_fields),
                "masked_field_count": len(masked_fields),
                "requires_aggregate": compiled_query.requires_aggregate,
                "compiled_filter_keys": sorted(compiled_query.filters.keys()),
            }

            digest_payload = {
                "tenant_id": scope.tenant_id,
                "user_id": scope.user_id,
                "session_id": scope.session_id,
                "pipeline_id": pipeline_id,
                "query_text": query_text,
                "intent_hash": intent_hash,
                "domain": compiled_query.domain,
                "source_type": compiled_query.source_type,
                "source_binding_id": compiled_query.source_binding_id,
                "data_source_id": compiled_query.data_source_id,
                "compiled_signature": compiled_query.parameterized_signature,
                "scope_snapshot": scope_snapshot,
                "policy_snapshot": policy_snapshot,
                "masked_fields": masked_fields,
                "reasoning": reasoning,
                "generated_at": now.isoformat(),
            }

            proof = PolicyProofArtifact(
                proof_id=str(uuid4()),
                proof_digest=self._digest(digest_payload),
                tenant_id=scope.tenant_id,
                user_id=scope.user_id,
                session_id=scope.session_id,
                pipeline_id=pipeline_id,
                query_text=query_text,
                intent_hash=intent_hash,
                domain=compiled_query.domain,
                source_type=compiled_query.source_type,
                source_binding_id=compiled_query.source_binding_id,
                data_source_id=compiled_query.data_source_id,
                compiled_signature=compiled_query.parameterized_signature,
                scope_snapshot=scope_snapshot,
                policy_snapshot=policy_snapshot,
                masked_fields=masked_fields,
                reasoning=reasoning,
                created_at=now,
            )
            db.add(proof)
            proof_ids.append(proof.proof_id)

        db.commit()
        return proof_ids


policy_proof_service = PolicyProofService()
