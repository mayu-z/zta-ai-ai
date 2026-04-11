from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.core.exceptions import AuthorizationError, ValidationError
from app.core.security import build_intent_hash
from app.interpreter.aliaser import apply_schema_aliasing
from app.interpreter.cache import intent_cache_service
from app.interpreter.domain_gate import detect_domains, enforce_domain_gate, normalize_domain
from app.interpreter.intent_extractor import IntentRule, extract_intent
from app.interpreter.registry import (
    derive_domain_keywords_from_intent_rules,
    load_domain_keywords,
    load_intent_detection_keywords,
    load_intent_rules,
)
from app.interpreter.sanitizer import sanitize_prompt
from app.schemas.pipeline import InterpreterOutput, ScopeContext


_SEMANTIC_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "get",
    "give",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "show",
    "the",
    "to",
    "what",
    "with",
}


class InterpreterService:
    def _load_interpreter_configuration(
        self,
        db: Session,
        tenant_id: str,
    ) -> tuple[
        dict[str, tuple[str, ...]],
        tuple[str, ...],
        tuple,
        dict[str, dict[str, list[str]]],
    ]:
        intent_rules = load_intent_rules(db, tenant_id)
        detection_keywords = load_intent_detection_keywords(db, tenant_id)

        try:
            domain_keywords, aggregation_modifiers = load_domain_keywords(db, tenant_id)
        except ValidationError as exc:
            if exc.code != "DOMAIN_KEYWORDS_NOT_CONFIGURED":
                raise

            domain_keywords = derive_domain_keywords_from_intent_rules(intent_rules)
            if not domain_keywords:
                raise
            aggregation_modifiers = tuple()

        return (
            domain_keywords,
            aggregation_modifiers,
            intent_rules,
            detection_keywords,
        )

    def _ordered_allowed_domains(self, scope: ScopeContext) -> list[str]:
        ordered: list[str] = []
        for raw_domain in scope.allowed_domains:
            normalized = normalize_domain(raw_domain)
            if normalized and normalized not in ordered:
                ordered.append(normalized)
        return ordered

    def _fallback_domain_for_undetermined(
        self,
        prompt: str,
        scope: ScopeContext,
    ) -> str | None:
        lower_prompt = prompt.lower()
        summary_markers = (
            "summary",
            "overview",
            "dashboard",
            "status",
            "snapshot",
            "quick view",
        )
        if not any(marker in lower_prompt for marker in summary_markers):
            return None

        allowed_domains = self._ordered_allowed_domains(scope)
        if not allowed_domains:
            return None

        for preferred in allowed_domains:
            if preferred != "notices":
                return preferred

        return allowed_domains[0]

    def _semantic_prompt_tokens(self, prompt: str) -> set[str]:
        return {
            token
            for token in re.findall(r"[a-z0-9_]{3,}", prompt.lower())
            if token not in _SEMANTIC_STOPWORDS
        }

    def _semantic_rule_terms(
        self,
        rule: IntentRule,
        detection_keywords: dict[str, dict[str, list[str]]],
    ) -> set[str]:
        terms: set[str] = set()
        by_type = detection_keywords.get(rule.name, {})
        detection_terms = [keyword for values in by_type.values() for keyword in values]

        candidates = [
            rule.name,
            rule.domain,
            rule.entity_type,
            *rule.keywords,
            *rule.slot_keys,
            *detection_terms,
        ]
        for candidate in candidates:
            normalized = str(candidate).strip().lower().replace("-", "_")
            if not normalized:
                continue
            terms.update(self._semantic_prompt_tokens(normalized.replace("_", " ")))

        return terms

    def _semantic_domain_for_undetermined(
        self,
        prompt: str,
        scope: ScopeContext,
        intent_rules: tuple[IntentRule, ...],
        detection_keywords: dict[str, dict[str, list[str]]],
    ) -> str | None:
        prompt_tokens = self._semantic_prompt_tokens(prompt)
        if not prompt_tokens:
            return None

        allowed_domains = set(self._ordered_allowed_domains(scope))
        domain_scores: dict[str, tuple[int, int, int]] = {}

        for rule in intent_rules:
            if rule.persona_types and scope.persona_type not in rule.persona_types:
                continue

            domain = normalize_domain(rule.domain)
            if scope.persona_type != "it_head" and allowed_domains and domain not in allowed_domains:
                continue

            rule_terms = self._semantic_rule_terms(rule, detection_keywords)
            overlap = len(prompt_tokens.intersection(rule_terms))
            if overlap == 0:
                continue

            score = (overlap, 1 if rule.is_default else 0, -rule.priority)
            current = domain_scores.get(domain)
            if current is None or score > current:
                domain_scores[domain] = score

        if not domain_scores:
            return None

        return max(domain_scores.items(), key=lambda item: item[1])[0]

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

    def _resolve_detected_domains(
        self,
        scope: ScopeContext,
        sanitized_prompt: str,
        domain_keywords: dict[str, tuple[str, ...]],
        aggregation_modifiers: tuple[str, ...],
        intent_rules: tuple[IntentRule, ...],
        detection_keywords: dict[str, dict[str, list[str]]],
    ) -> list[str]:
        detected_domains = detect_domains(
            sanitized_prompt,
            domain_keywords=domain_keywords,
            aggregation_modifiers=aggregation_modifiers,
            persona_type=scope.persona_type,
        )

        if not detected_domains:
            semantic_domain = self._semantic_domain_for_undetermined(
                sanitized_prompt,
                scope,
                intent_rules,
                detection_keywords,
            )
            fallback_domain = semantic_domain or self._fallback_domain_for_undetermined(
                sanitized_prompt,
                scope,
            )
            if fallback_domain:
                detected_domains = [fallback_domain]
            else:
                allowed_domains = self._ordered_allowed_domains(scope)
                allowed_display = ", ".join(allowed_domains) or "none"
                raise ValidationError(
                    message=(
                        "Unable to match your prompt to a known domain keyword. "
                        f"Try phrasing the request using one of your allowed domains: {allowed_display}."
                    ),
                    code="DOMAIN_UNDETERMINED",
                )

        if scope.persona_type != "it_head":
            enforce_domain_gate(detected_domains, scope.allowed_domains)

        return detected_domains

    def _build_output(
        self,
        db: Session,
        scope: ScopeContext,
        prompt: str,
        sanitized_prompt: str,
        detected_domains: list[str],
        intent_rules,
        detection_keywords: dict[str, dict[str, list[str]]],
    ) -> InterpreterOutput:
        aliased_prompt, real_identifiers = apply_schema_aliasing(
            db, scope.tenant_id, sanitized_prompt
        )
        
        intent = extract_intent(
            raw_prompt=prompt,
            sanitized_prompt=sanitized_prompt,
            aliased_prompt=aliased_prompt,
            detected_domains=detected_domains,
            persona_type=scope.persona_type,
            intent_rules=intent_rules,
            detection_keywords=detection_keywords,
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

    def run(self, db: Session, scope: ScopeContext, prompt: str) -> InterpreterOutput:
        sanitized_prompt, _removed_patterns = sanitize_prompt(prompt)

        self._enforce_student_scope(sanitized_prompt, scope)
        self._enforce_executive_aggregate_only(sanitized_prompt, scope)

        (
            domain_keywords,
            aggregation_modifiers,
            intent_rules,
            detection_keywords,
        ) = self._load_interpreter_configuration(db, scope.tenant_id)

        detected_domains = self._resolve_detected_domains(
            scope,
            sanitized_prompt,
            domain_keywords,
            aggregation_modifiers,
            intent_rules,
            detection_keywords,
        )

        return self._build_output(
            db,
            scope,
            prompt,
            sanitized_prompt,
            detected_domains,
            intent_rules,
            detection_keywords,
        )

    def run_for_domain(
        self,
        db: Session,
        scope: ScopeContext,
        prompt: str,
        domain: str,
    ) -> InterpreterOutput:
        sanitized_prompt, _removed_patterns = sanitize_prompt(prompt)

        self._enforce_student_scope(sanitized_prompt, scope)
        self._enforce_executive_aggregate_only(sanitized_prompt, scope)

        (
            domain_keywords,
            aggregation_modifiers,
            intent_rules,
            detection_keywords,
        ) = self._load_interpreter_configuration(db, scope.tenant_id)

        detected_domains = self._resolve_detected_domains(
            scope,
            sanitized_prompt,
            domain_keywords,
            aggregation_modifiers,
            intent_rules,
            detection_keywords,
        )

        if domain not in detected_domains:
            raise ValidationError(
                message="Requested domain is not present in the detected domain set",
                code="DOMAIN_NOT_DETECTED",
            )

        return self._build_output(
            db,
            scope,
            prompt,
            sanitized_prompt,
            [domain],
            intent_rules,
            detection_keywords,
        )


interpreter_service = InterpreterService()
