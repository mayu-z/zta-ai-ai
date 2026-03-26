from __future__ import annotations

import time
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.compiler.service import compiler_service
from app.core.exceptions import AuthorizationError, ZTAError
from app.interpreter.cache import intent_cache_service
from app.interpreter.service import interpreter_service
from app.policy.engine import policy_engine
from app.schemas.pipeline import AuditEvent, PipelineResult, ScopeContext
from app.services.audit_service import audit_service
from app.services.history_service import history_service
from app.slm.output_guard import output_guard
from app.slm.simulator import slm_simulator
from app.tool_layer.service import tool_layer_service


class PipelineService:
    def process_query(self, db: Session, scope: ScopeContext, query_text: str) -> PipelineResult:
        started = time.perf_counter()
        intent_hash = ""
        domains: list[str] = []

        history_service.append(scope.tenant_id, scope.user_id, scope.session_id, "user", query_text)

        try:
            if scope.persona_type == "it_head":
                raise AuthorizationError(
                    message="IT Head is restricted to admin dashboard and cannot access business data chat",
                    code="IT_HEAD_CHAT_BLOCKED",
                )

            interpreter_output = interpreter_service.run(db, scope, query_text)
            intent_hash = interpreter_output.intent_hash
            domains = [interpreter_output.intent.domain]

            template = interpreter_output.cached_template
            cache_hit = template is not None
            if not template:
                template = slm_simulator.render_template(interpreter_output.intent, scope)

            output_guard.validate(template, interpreter_output.schema_real_identifiers)

            compiled_query = compiler_service.compile_intent(scope, interpreter_output.intent)
            policy_engine.authorize(scope, interpreter_output.intent, compiled_query)

            values = tool_layer_service.execute(db, compiled_query)
            masked_values, masked_fields_applied = policy_engine.apply_field_masking(values, scope.masked_fields)

            final_response = compiler_service.detokenize(
                template=template,
                query_plan=compiled_query,
                values=masked_values,
                masked_fields_applied=masked_fields_applied,
            )

            latency_ms = int((time.perf_counter() - started) * 1000)

            if not cache_hit:
                intent_cache_service.set(
                    db=db,
                    tenant_id=scope.tenant_id,
                    intent_hash=interpreter_output.intent_hash,
                    normalized_intent=interpreter_output.intent.normalized(),
                    response_template=template,
                    compiled_query=compiled_query.model_dump(mode="json"),
                )

            history_service.append(scope.tenant_id, scope.user_id, scope.session_id, "assistant", final_response)

            audit_service.enqueue(
                AuditEvent(
                    tenant_id=scope.tenant_id,
                    user_id=scope.user_id,
                    session_id=scope.session_id,
                    query_text=query_text,
                    intent_hash=interpreter_output.intent_hash,
                    domains_accessed=domains,
                    was_blocked=False,
                    block_reason=None,
                    response_summary=final_response,
                    latency_ms=latency_ms,
                    created_at=datetime.now(tz=UTC),
                )
            )

            return PipelineResult(
                response_text=final_response,
                source=compiled_query.source_type,
                latency_ms=latency_ms,
                intent_hash=interpreter_output.intent_hash,
                domains_accessed=domains,
                was_blocked=False,
            )

        except ZTAError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            fallback_hash = intent_hash or "0" * 64
            audit_service.enqueue(
                AuditEvent(
                    tenant_id=scope.tenant_id,
                    user_id=scope.user_id,
                    session_id=scope.session_id,
                    query_text=query_text,
                    intent_hash=fallback_hash,
                    domains_accessed=domains,
                    was_blocked=True,
                    block_reason=exc.code,
                    response_summary=exc.message,
                    latency_ms=latency_ms,
                    created_at=datetime.now(tz=UTC),
                )
            )
            raise


pipeline_service = PipelineService()
