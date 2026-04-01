from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import cast

from sqlalchemy.orm import Session

from app.compiler.service import compiler_service
from app.core.exceptions import AuthorizationError, ZTAError
from app.interpreter.cache import intent_cache_service
from app.interpreter.conversational import detect_conversational_query, is_unclear_query
from app.interpreter.service import interpreter_service
from app.policy.engine import policy_engine
from app.schemas.pipeline import AuditEvent, PipelineResult, ScopeContext
from app.services.audit_service import audit_service
from app.services.history_service import history_service
from app.services.pipeline_monitor import pipeline_monitor
from app.slm.output_guard import output_guard
from app.slm.simulator import slm_simulator
from app.tool_layer.service import tool_layer_service


class PipelineService:
    @contextmanager
    def _track_stage(
        self,
        pipeline_id: str,
        stage_name: str,
        stage_index: int,
        metadata: dict | None = None,
    ):
        """
        Context manager to track individual pipeline stage execution.

        Emits started/completed/error events to Redis pub/sub for real-time monitoring.
        """
        start_time = time.perf_counter()
        pipeline_monitor.emit_stage_event(
            pipeline_id=pipeline_id,
            stage_name=stage_name,
            stage_index=stage_index,
            status="started",
            metadata=metadata or {},
        )

        try:
            yield
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            pipeline_monitor.emit_stage_event(
                pipeline_id=pipeline_id,
                stage_name=stage_name,
                stage_index=stage_index,
                status="completed",
                duration_ms=duration_ms,
            )
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            pipeline_monitor.emit_stage_event(
                pipeline_id=pipeline_id,
                stage_name=stage_name,
                stage_index=stage_index,
                status="error",
                duration_ms=duration_ms,
                error_message=str(exc),
            )
            raise

    def process_query(
        self, db: Session, scope: ScopeContext, query_text: str
    ) -> PipelineResult:
        pipeline_id = str(uuid.uuid4())
        started = time.perf_counter()
        intent_hash = ""
        domains: list[str] = []

        # Emit pipeline start metadata for monitoring
        pipeline_monitor.emit_pipeline_start(
            pipeline_id=pipeline_id,
            tenant_id=scope.tenant_id,
            user_id=scope.user_id,
            session_id=scope.session_id,
            query_text=query_text,
        )

        # Stage 0: Store user message in history
        with self._track_stage(pipeline_id, "history_user_message", 0):
            history_service.append(
                scope.tenant_id, scope.user_id, scope.session_id, "user", query_text
            )

        # Stage 0.5: Check for conversational queries (greetings, help, etc.)
        conversational = detect_conversational_query(query_text)
        if conversational.is_conversational:
            latency_ms = int((time.perf_counter() - started) * 1000)
            response_text = conversational.response or "Hello! How can I help you?"

            # Store assistant response in history
            history_service.append(
                scope.tenant_id,
                scope.user_id,
                scope.session_id,
                "assistant",
                response_text,
            )

            # Emit pipeline completion for conversational query
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id, status="success", total_duration_ms=latency_ms
            )

            return PipelineResult(
                response_text=response_text,
                source="conversational",
                latency_ms=latency_ms,
                intent_hash="conversational",
                domains_accessed=[],
                was_blocked=False,
            )

        # Stage 0.6: Check for unclear queries (no data keywords)
        unclear = is_unclear_query(query_text)
        if unclear.is_conversational:
            latency_ms = int((time.perf_counter() - started) * 1000)
            response_text = (
                unclear.response
                or "I'm not sure what you're looking for. Could you please rephrase your question?"
            )

            # Store assistant response in history
            history_service.append(
                scope.tenant_id,
                scope.user_id,
                scope.session_id,
                "assistant",
                response_text,
            )

            # Emit pipeline completion for unclear query
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id, status="success", total_duration_ms=latency_ms
            )

            return PipelineResult(
                response_text=response_text,
                source="clarification",
                latency_ms=latency_ms,
                intent_hash="unclear",
                domains_accessed=[],
                was_blocked=False,
            )

        try:
            # Stage 1: Interpreter layer (sanitizer, domain gate, aliaser, intent extraction)
            with self._track_stage(pipeline_id, "interpreter", 1):
                interpreter_output = interpreter_service.run(db, scope, query_text)
                intent_hash = interpreter_output.intent_hash
                domains = [interpreter_output.intent.domain]

            # Stage 2: Intent cache check
            with self._track_stage(
                pipeline_id,
                "intent_cache",
                2,
                {"intent_hash": interpreter_output.intent_hash[:16]},
            ):
                template = interpreter_output.cached_template
                cache_hit = template is not None

            # Stage 3: SLM render (conditional on cache miss)
            if not cache_hit:
                with self._track_stage(pipeline_id, "slm_render", 3):
                    template = slm_simulator.render_template(
                        interpreter_output.intent, scope
                    )
            else:
                # Emit skipped event if cache hit
                pipeline_monitor.emit_stage_event(
                    pipeline_id=pipeline_id,
                    stage_name="slm_render",
                    stage_index=3,
                    status="skipped",
                    metadata={"reason": "cache_hit"},
                )

            # At this point template is guaranteed to exist (cache hit or SLM render).
            safe_template = cast(str, template)

            # Stage 4: Output guard validation
            with self._track_stage(pipeline_id, "output_guard", 4):
                output_guard.validate(
                    safe_template, interpreter_output.schema_real_identifiers
                )

            # Stage 5: Compiler (query plan generation)
            with self._track_stage(pipeline_id, "compiler", 5):
                compiled_query = compiler_service.compile_intent(
                    scope, interpreter_output.intent
                )

            # Stage 6: Policy authorization (handles IT Head non-admin blocking)
            with self._track_stage(pipeline_id, "policy_authorization", 6):
                policy_engine.authorize(
                    scope, interpreter_output.intent, compiled_query
                )

            # Stage 7: Tool layer execution
            with self._track_stage(pipeline_id, "tool_execution", 7):
                values = tool_layer_service.execute(db, compiled_query)

            # Stage 8: Field masking
            with self._track_stage(pipeline_id, "field_masking", 8):
                masked_values, masked_fields_applied = (
                    policy_engine.apply_field_masking(values, scope.masked_fields)
                )

            # Stage 9: Detokenization
            with self._track_stage(pipeline_id, "detokenization", 9):
                final_response = compiler_service.detokenize(
                    template=safe_template,
                    query_plan=compiled_query,
                    values=masked_values,
                    masked_fields_applied=masked_fields_applied,
                )

            latency_ms = int((time.perf_counter() - started) * 1000)

            # Stage 10: Cache storage (conditional on cache miss)
            if not cache_hit:
                with self._track_stage(pipeline_id, "cache_storage", 10):
                    intent_cache_service.set(
                        db=db,
                        tenant_id=scope.tenant_id,
                        intent_hash=interpreter_output.intent_hash,
                        normalized_intent=interpreter_output.intent.normalized(),
                        response_template=safe_template,
                        compiled_query=compiled_query.model_dump(mode="json"),
                    )
            else:
                # Emit skipped event if cache hit
                pipeline_monitor.emit_stage_event(
                    pipeline_id=pipeline_id,
                    stage_name="cache_storage",
                    stage_index=10,
                    status="skipped",
                    metadata={"reason": "cache_hit"},
                )

            # Stage 11: Store assistant message in history
            with self._track_stage(pipeline_id, "history_assistant_message", 11):
                history_service.append(
                    scope.tenant_id,
                    scope.user_id,
                    scope.session_id,
                    "assistant",
                    final_response,
                )

            # Stage 12: Audit logging
            with self._track_stage(pipeline_id, "audit_logging", 12):
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

            # Emit pipeline completion
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id, status="success", total_duration_ms=latency_ms
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

            # Still log audit even on error
            with self._track_stage(pipeline_id, "audit_logging_error", 12):
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

            # Emit pipeline failure
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id,
                status="error",
                total_duration_ms=latency_ms,
                final_message=exc.message,
            )

            raise


pipeline_service = PipelineService()
