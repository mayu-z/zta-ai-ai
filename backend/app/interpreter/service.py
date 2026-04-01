from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError
from app.core.security import build_intent_hash
from app.interpreter.aliaser import apply_schema_aliasing
from app.interpreter.cache import intent_cache_service
from app.interpreter.domain_gate import detect_domains, enforce_domain_gate
from app.interpreter.intent_extractor import extract_intent
from app.interpreter.sanitizer import sanitize_prompt
from app.schemas.pipeline import InterpreterOutput, ScopeContext


class InterpreterService:
    def _enforce_student_scope(self, prompt: str, scope: ScopeContext) -> None:
        if scope.persona_type != "student":
            return

        external_ids = re.findall(r"\b[A-Z]{2,5}-\d{2,8}\b", prompt)
        for identifier in external_ids:
            if identifier != scope.external_id:
                raise AuthorizationError(
                    message="Student scope violation: cross-student access attempt detected",
                    code="STUDENT_SCOPE_BLOCKED",
                )

        if re.search(
            r"\b(all students|other students|another student)\b",
            prompt,
            flags=re.IGNORECASE,
        ):
            raise AuthorizationError(
                message="Student scope violation: aggregate student access is not allowed",
                code="STUDENT_SCOPE_BLOCKED",
            )

    def _enforce_executive_aggregate_only(
        self, prompt: str, scope: ScopeContext
    ) -> None:
        if scope.persona_type != "executive" or not scope.aggregate_only:
            return

        # Block explicit requests for raw, individual, or person-level data
        raw_data_patterns = (
            r"\braw\s+(student|data|record)",
            r"\b(individual|person|specific)\s+(student|record|data)",
            r"\bstudent\s+records?\b",
            r"\blist\s+(all\s+)?students\b",
            r"\bshow\s+(me\s+)?(all\s+)?students\b",
        )
        for pattern in raw_data_patterns:
            if re.search(pattern, prompt, flags=re.IGNORECASE):
                raise AuthorizationError(
                    message="Executive access is restricted to aggregate data only",
                    code="EXEC_AGGREGATE_ONLY",
                )

    def run(self, db: Session, scope: ScopeContext, prompt: str) -> InterpreterOutput:
        sanitized_prompt, _removed_patterns = sanitize_prompt(prompt)

        self._enforce_student_scope(sanitized_prompt, scope)
        self._enforce_executive_aggregate_only(sanitized_prompt, scope)

        detected_domains = detect_domains(sanitized_prompt)
        if scope.persona_type != "it_head":
            enforce_domain_gate(detected_domains, scope.allowed_domains)

        aliased_prompt, real_identifiers = apply_schema_aliasing(
            db, scope.tenant_id, sanitized_prompt
        )

        intent = extract_intent(
            raw_prompt=prompt,
            sanitized_prompt=sanitized_prompt,
            aliased_prompt=aliased_prompt,
            detected_domains=detected_domains,
            persona_type=scope.persona_type,
        )

        if scope.persona_type == "executive":
            intent.aggregation = "aggregate"

        normalized_intent = intent.normalized()
        intent_hash = build_intent_hash(normalized_intent, scope.tenant_id)

        cached = intent_cache_service.get(db, scope.tenant_id, intent_hash)

        return InterpreterOutput(
            intent=intent,
            intent_hash=intent_hash,
            cached_template=(cached or {}).get("response_template"),
            cached_compiled_query=(cached or {}).get("compiled_query"),
            schema_real_identifiers=real_identifiers,
        )


interpreter_service = InterpreterService()
