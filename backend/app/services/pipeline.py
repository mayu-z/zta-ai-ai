from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compiler.service import compiler_service
from app.core.exceptions import ZTAError
from app.db.models import ControlGraphEdge, ControlGraphNode
from app.agentic.runtime_bridge import agentic_runtime_bridge
from app.interpreter.cache import intent_cache_service
from app.interpreter.conversational import detect_conversational_query, is_unclear_query
from app.interpreter.service import interpreter_service
from app.policy.engine import policy_engine
from app.schemas.pipeline import (
    AuditEvent,
    CompiledQueryPlan,
    InterpreterOutput,
    PipelineResult,
    PolicyDecision,
    ScopeContext,
)
from app.services.audit_service import audit_service
from app.services.history_service import history_service
from app.services.pipeline_monitor import pipeline_monitor
from app.services.policy_proof_service import policy_proof_service
from app.slm.output_guard import output_guard
from app.slm.simulator import slm_simulator
from app.tool_layer.service import tool_layer_service

logger = logging.getLogger(__name__)


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

    def _compute_latency_flag(self, latency_ms: int) -> str:
        if 500 <= latency_ms <= 2000:
            return "normal"
        if latency_ms > 500:
            return "high"
        return "suspicious"

    def _enqueue_audit_event(
        self,
        *,
        scope: ScopeContext,
        query_text: str,
        intent_hash: str,
        domains_accessed: list[str],
        was_blocked: bool,
        block_reason: str | None,
        response_summary: str,
        latency_ms: int,
    ) -> None:
        latency_flag = self._compute_latency_flag(latency_ms)
        if latency_flag != "normal":
            logger.warning(
                "Non-normal latency detected for query audit event: latency_ms=%s, latency_flag=%s, tenant_id=%s, user_id=%s",
                latency_ms,
                latency_flag,
                scope.tenant_id,
                scope.user_id,
            )

        audit_service.enqueue(
            AuditEvent(
                tenant_id=scope.tenant_id,
                user_id=scope.user_id,
                session_id=scope.session_id,
                query_text=query_text,
                intent_hash=intent_hash,
                domains_accessed=domains_accessed,
                was_blocked=was_blocked,
                block_reason=block_reason,
                response_summary=response_summary,
                latency_ms=latency_ms,
                latency_flag=latency_flag,
                created_at=datetime.now(tz=UTC),
            )
        )

    def _is_multi_domain_prompt(self, query_text: str) -> bool:
        lower_query = query_text.lower()
        return bool(
            re.search(
                r"\b(and|also|plus|along with|as well as|both)\b",
                lower_query,
            )
        )

    def _select_secondary_domain(
        self,
        scope: ScopeContext,
        primary_domain: str,
        detected_domains: list[str],
        query_text: str,
    ) -> str | None:
        if len(detected_domains) < 2:
            return None
        if not self._is_multi_domain_prompt(query_text):
            return None

        if scope.persona_type == "student":
            supported_domains = {"academic", "finance"}
        elif scope.persona_type == "faculty":
            supported_domains = {"academic", "hr", "notices"}
        else:
            return None

        if primary_domain not in supported_domains:
            return None

        for domain in detected_domains:
            if domain != primary_domain and domain in supported_domains:
                return domain

        return None

    def _compose_multi_domain_response(
        self,
        domain_responses: list[tuple[str, str]],
    ) -> str:
        if not domain_responses:
            return ""
        if len(domain_responses) == 1:
            return domain_responses[0][1]

        sections: list[str] = []
        for domain, response_text in domain_responses:
            label = domain.replace("_", " ").title()
            sections.append(f"{label}: {response_text}")

        return "\n\n".join(sections)

    def _append_course_scope_context(
        self,
        *,
        response_text: str,
        scope: ScopeContext,
        query_text: str,
    ) -> str:
        if scope.persona_type != "faculty":
            return response_text
        if not scope.course_ids:
            return response_text

        lower_query = query_text.lower()
        if not any(marker in lower_query for marker in ("course", "courses", "teaching", "handling")):
            return response_text

        if any(course_id in response_text for course_id in scope.course_ids):
            return response_text

        course_list = ", ".join(scope.course_ids)
        return f"{response_text} Courses in your scope: {course_list}."

    def _build_graph_reasoning_context(
        self,
        *,
        db: Session,
        scope: ScopeContext,
        intent_domain: str,
    ) -> dict[str, object] | None:
        domain_node = db.scalar(
            select(ControlGraphNode).where(
                ControlGraphNode.tenant_id == scope.tenant_id,
                ControlGraphNode.node_type == "domain",
                ControlGraphNode.node_key == intent_domain,
            )
        )
        if domain_node is None:
            return None

        bound_sources: list[str] = []
        edge_rows = db.scalars(
            select(ControlGraphEdge).where(
                ControlGraphEdge.tenant_id == scope.tenant_id,
                ControlGraphEdge.edge_type == "domain_bound_to_source",
                ControlGraphEdge.source_node_id == domain_node.id,
            )
        ).all()
        for edge in edge_rows:
            target_node = db.scalar(
                select(ControlGraphNode).where(
                    ControlGraphNode.tenant_id == scope.tenant_id,
                    ControlGraphNode.id == edge.target_node_id,
                )
            )
            if target_node is None:
                continue
            if target_node.node_type == "data_source":
                source_type = ""
                if isinstance(target_node.attributes, dict):
                    source_type = str(target_node.attributes.get("source_type") or "")
                label = source_type or target_node.label or target_node.node_key
                if label:
                    bound_sources.append(str(label))
            elif target_node.node_type == "source_type":
                bound_sources.append(target_node.node_key)

        return {
            "domain": intent_domain,
            "role_key": scope.role_key or scope.persona_type,
            "bound_sources": list(dict.fromkeys(bound_sources)),
            "masked_fields": scope.masked_fields,
        }

    def process_query(
        self, db: Session, scope: ScopeContext, query_text: str
    ) -> PipelineResult:
        pipeline_id = str(uuid.uuid4())
        started = time.perf_counter()
        intent_hash = ""
        domains: list[str] = []
        policy_proof_ids: list[str] = []

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

            self._enqueue_audit_event(
                scope=scope,
                query_text=query_text,
                intent_hash="conversational",
                domains_accessed=[],
                was_blocked=False,
                block_reason=None,
                response_summary=response_text,
                latency_ms=latency_ms,
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

            self._enqueue_audit_event(
                scope=scope,
                query_text=query_text,
                intent_hash="unclear",
                domains_accessed=[],
                was_blocked=False,
                block_reason=None,
                response_summary=response_text,
                latency_ms=latency_ms,
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
            # Stage A: Agentic routing (enforced chain for enabled agentic actions)
            with self._track_stage(pipeline_id, "agentic_routing", 1):
                agentic_outcome = agentic_runtime_bridge.maybe_execute(
                    query_text=query_text,
                    scope=scope,
                )

            if agentic_outcome is not None:
                latency_ms = int((time.perf_counter() - started) * 1000)
                response_text = self._append_course_scope_context(
                    response_text=agentic_outcome.response_text,
                    scope=scope,
                    query_text=query_text,
                )

                history_service.append(
                    scope.tenant_id,
                    scope.user_id,
                    scope.session_id,
                    "assistant",
                    response_text,
                )

                self._enqueue_audit_event(
                    scope=scope,
                    query_text=query_text,
                    intent_hash=agentic_outcome.intent_hash,
                    domains_accessed=agentic_outcome.domains_accessed,
                    was_blocked=agentic_outcome.was_blocked,
                    block_reason=agentic_outcome.block_reason,
                    response_summary=response_text,
                    latency_ms=latency_ms,
                )

                pipeline_monitor.emit_pipeline_complete(
                    pipeline_id=pipeline_id,
                    status="success",
                    total_duration_ms=latency_ms,
                )

                return PipelineResult(
                    response_text=response_text,
                    source=agentic_outcome.source,
                    latency_ms=latency_ms,
                    intent_hash=agentic_outcome.intent_hash,
                    domains_accessed=agentic_outcome.domains_accessed,
                    was_blocked=agentic_outcome.was_blocked,
                    block_reason=agentic_outcome.block_reason,
                )

            # Stage 1: Interpreter layer (sanitizer, domain gate, aliaser, intent extraction)
            with self._track_stage(pipeline_id, "interpreter", 1):
                primary_output = interpreter_service.run(db, scope, query_text)
                intent_hash = primary_output.intent_hash
                domains = [primary_output.intent.domain]
                interpreter_outputs: list[InterpreterOutput] = [primary_output]

                secondary_domain = self._select_secondary_domain(
                    scope=scope,
                    primary_domain=primary_output.intent.domain,
                    detected_domains=primary_output.intent.detected_domains,
                    query_text=query_text,
                )
                if secondary_domain is not None:
                    secondary_output = interpreter_service.run_for_domain(
                        db,
                        scope,
                        query_text,
                        secondary_domain,
                    )
                    if secondary_output.intent.domain != primary_output.intent.domain:
                        interpreter_outputs.append(secondary_output)
                        domains.append(secondary_output.intent.domain)

                domains = list(dict.fromkeys(domains))

            interpreter_output = interpreter_outputs[0]

            logger.info(
                "Pipeline intent resolved: pipeline_id=%s tenant_id=%s user_id=%s intent=%s domain=%s detected_domains=%s slot_keys=%s",
                pipeline_id,
                scope.tenant_id,
                scope.user_id,
                interpreter_output.intent.name,
                interpreter_output.intent.domain,
                interpreter_output.intent.detected_domains,
                interpreter_output.intent.slot_keys,
            )

            if len(interpreter_outputs) > 1:
                logger.info(
                    "Pipeline multi-domain merge enabled: pipeline_id=%s tenant_id=%s user_id=%s primary_domain=%s secondary_domain=%s",
                    pipeline_id,
                    scope.tenant_id,
                    scope.user_id,
                    interpreter_outputs[0].intent.domain,
                    interpreter_outputs[1].intent.domain,
                )

            DIRECT_RENDER_INTENTS = {"admin_audit_log", "admin_data_sources"}
            if (
                len(interpreter_outputs) == 1
                and interpreter_output.intent.name in DIRECT_RENDER_INTENTS
            ):
                with self._track_stage(pipeline_id, "compiler", 2):
                    compiled_query = compiler_service.compile_intent(
                        scope, interpreter_output.intent, db
                    )
                with self._track_stage(pipeline_id, "policy_authorization", 3):
                    policy_decision = policy_engine.authorize(
                        scope, interpreter_output.intent, compiled_query
                    )
                with self._track_stage(pipeline_id, "tool_execution", 4):
                    values = tool_layer_service.execute(db, compiled_query)

                with self._track_stage(pipeline_id, "policy_proof", 5):
                    policy_proof_ids = policy_proof_service.persist_query_proofs(
                        db=db,
                        scope=scope,
                        query_text=query_text,
                        intent_hash=interpreter_output.intent_hash,
                        pipeline_id=pipeline_id,
                        proofs=[
                            {
                                "compiled_query": compiled_query,
                                "policy_decision": policy_decision,
                                "masked_fields": [],
                            }
                        ],
                    )

                latency_ms = int((time.perf_counter() - started) * 1000)

                if interpreter_output.intent.name == "admin_audit_log":
                    raw_entries = values.get("entries", [])
                    entries = (
                        cast(list[dict[str, object]], raw_entries)
                        if isinstance(raw_entries, list)
                        else []
                    )
                    if not entries:
                        final_response = "No audit log entries found."
                    else:
                        lines = []
                        for i, item in enumerate(entries[:10], 1):
                            query = str(item.get("query_text", "unknown"))
                            blocked = bool(item.get("was_blocked", False))
                            timestamp = str(item.get("created_at", ""))[:16]
                            status = "BLOCKED" if blocked else "ALLOWED"
                            lines.append(f"{i}. [{status}] {query} ({timestamp})")
                        final_response = "Recent audit log entries:\n" + "\n".join(lines)
                elif interpreter_output.intent.name == "admin_data_sources":
                    raw_sources = values.get("sources", [])
                    sources = (
                        cast(list[dict[str, object]], raw_sources)
                        if isinstance(raw_sources, list)
                        else []
                    )
                    if not sources:
                        final_response = "No data sources configured."
                    else:
                        lines = []
                        for i, item in enumerate(sources, 1):
                            name = str(item.get("name", "unknown"))
                            status = str(item.get("status", "unknown"))
                            source_type = str(item.get("source_type", ""))
                            lines.append(f"{i}. {name} ({source_type}) — {status}")
                        final_response = "Connected data sources:\n" + "\n".join(lines)

                final_response = self._append_course_scope_context(
                    response_text=final_response,
                    scope=scope,
                    query_text=query_text,
                )

                history_service.append(
                    scope.tenant_id,
                    scope.user_id,
                    scope.session_id,
                    "assistant",
                    final_response,
                )
                audit_service.enqueue(
                    AuditEvent(
                        tenant_id=scope.tenant_id,
                        user_id=scope.user_id,
                        session_id=scope.session_id,
                        query_text=query_text,
                        intent_hash=interpreter_output.intent_hash,
                        domains_accessed=[interpreter_output.intent.domain],
                        was_blocked=False,
                        block_reason=None,
                        response_summary=final_response,
                        latency_ms=latency_ms,
                        created_at=datetime.now(tz=UTC),
                    )
                )
                pipeline_monitor.emit_pipeline_complete(
                    pipeline_id=pipeline_id,
                    status="success",
                    total_duration_ms=latency_ms,
                )
                return PipelineResult(
                    response_text=final_response,
                    source="admin_direct",
                    latency_ms=latency_ms,
                    intent_hash=interpreter_output.intent_hash,
                    domains_accessed=[interpreter_output.intent.domain],
                    policy_proof_ids=policy_proof_ids,
                    was_blocked=False,
                )

            # Stage 2: Intent cache check
            with self._track_stage(
                pipeline_id,
                "intent_cache",
                2,
                {"intent_count": len(interpreter_outputs)},
            ):
                execution_units: list[dict[str, object]] = []
                for output in interpreter_outputs:
                    template = output.cached_template
                    execution_units.append(
                        {
                            "interpreter_output": output,
                            "template": template,
                            "cache_hit": template is not None,
                        }
                    )

            for unit in execution_units:
                unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                unit_cache_hit = bool(unit["cache_hit"])
                logger.info(
                    "Pipeline cache %s: pipeline_id=%s tenant_id=%s intent_hash_prefix=%s domain=%s",
                    "hit" if unit_cache_hit else "miss",
                    pipeline_id,
                    scope.tenant_id,
                    unit_output.intent_hash[:16],
                    unit_output.intent.domain,
                )

            # Stage 3: Compiler (query plan generation)
            with self._track_stage(
                pipeline_id,
                "compiler",
                3,
                {"intent_count": len(execution_units)},
            ):
                for unit in execution_units:
                    unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                    unit["compiled_query"] = compiler_service.compile_intent(
                        scope,
                        unit_output.intent,
                        db,
                    )

            # Stage 4: Policy authorization (handles IT Head non-admin blocking)
            with self._track_stage(
                pipeline_id,
                "policy_authorization",
                4,
                {"intent_count": len(execution_units)},
            ):
                for unit in execution_units:
                    unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                    compiled_query = cast(CompiledQueryPlan, unit["compiled_query"])
                    unit["policy_decision"] = policy_engine.authorize(
                        scope,
                        unit_output.intent,
                        compiled_query,
                    )

            # Stage 5: SLM render (conditional on cache miss)
            units_to_render = [unit for unit in execution_units if not bool(unit["cache_hit"])]
            if units_to_render:
                with self._track_stage(
                    pipeline_id,
                    "slm_render",
                    5,
                    {"render_count": len(units_to_render)},
                ):
                    for unit in units_to_render:
                        unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                        graph_context = self._build_graph_reasoning_context(
                            db=db,
                            scope=scope,
                            intent_domain=unit_output.intent.domain,
                        )
                        unit["template"] = slm_simulator.render_template(
                            unit_output.intent,
                            scope,
                            graph_context,
                        )
            else:
                # Emit skipped event if cache hit
                pipeline_monitor.emit_stage_event(
                    pipeline_id=pipeline_id,
                    stage_name="slm_render",
                    stage_index=5,
                    status="skipped",
                    metadata={"reason": "cache_hit"},
                )

            # Stage 6: Output guard validation
            with self._track_stage(
                pipeline_id,
                "output_guard",
                6,
                {"intent_count": len(execution_units)},
            ):
                for unit in execution_units:
                    unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                    safe_template = cast(str, unit["template"])
                    output_guard.validate(
                        safe_template,
                        unit_output.schema_real_identifiers,
                        expected_slot_count=len(unit_output.intent.slot_keys),
                    )

            # Stage 7: Tool layer execution
            with self._track_stage(
                pipeline_id,
                "tool_execution",
                7,
                {"intent_count": len(execution_units)},
            ):
                for unit in execution_units:
                    compiled_query = cast(CompiledQueryPlan, unit["compiled_query"])
                    unit["values"] = tool_layer_service.execute(db, compiled_query)

            # Stage 8: Field masking
            with self._track_stage(
                pipeline_id,
                "field_masking",
                8,
                {"intent_count": len(execution_units)},
            ):
                for unit in execution_units:
                    values = cast(dict[str, object], unit["values"])
                    masked_values, masked_fields_applied = policy_engine.apply_field_masking(
                        values,
                        scope.masked_fields,
                    )
                    unit["masked_values"] = masked_values
                    unit["masked_fields_applied"] = masked_fields_applied

            # Stage 9: Detokenization
            with self._track_stage(
                pipeline_id,
                "detokenization",
                9,
                {"intent_count": len(execution_units)},
            ):
                domain_responses: list[tuple[str, str]] = []
                for unit in execution_units:
                    unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                    safe_template = cast(str, unit["template"])
                    compiled_query = cast(CompiledQueryPlan, unit["compiled_query"])
                    masked_values = cast(dict[str, object], unit["masked_values"])
                    masked_fields_applied = cast(
                        list[str],
                        unit["masked_fields_applied"],
                    )

                    response_text = compiler_service.detokenize(
                        template=safe_template,
                        query_plan=compiled_query,
                        values=masked_values,
                        masked_fields_applied=masked_fields_applied,
                    )
                    unit["final_response"] = response_text
                    domain_responses.append((unit_output.intent.domain, response_text))

                final_response = self._compose_multi_domain_response(domain_responses)

            final_response = self._append_course_scope_context(
                response_text=final_response,
                scope=scope,
                query_text=query_text,
            )

            latency_ms = int((time.perf_counter() - started) * 1000)

            # Stage 10: Deterministic policy proof persistence
            with self._track_stage(
                pipeline_id,
                "policy_proof",
                10,
                {"intent_count": len(execution_units)},
            ):
                proof_payloads = [
                    {
                        "compiled_query": cast(CompiledQueryPlan, unit["compiled_query"]),
                        "policy_decision": cast(
                            PolicyDecision | None,
                            unit.get("policy_decision"),
                        ),
                        "masked_fields": cast(list[str], unit["masked_fields_applied"]),
                    }
                    for unit in execution_units
                ]
                policy_proof_ids = policy_proof_service.persist_query_proofs(
                    db=db,
                    scope=scope,
                    query_text=query_text,
                    intent_hash=interpreter_output.intent_hash,
                    pipeline_id=pipeline_id,
                    proofs=proof_payloads,
                )

            # Stage 11: Cache storage (conditional on cache miss)
            cache_miss_units = [unit for unit in execution_units if not bool(unit["cache_hit"])]
            if cache_miss_units:
                with self._track_stage(
                    pipeline_id,
                    "cache_storage",
                    11,
                    {"cache_write_count": len(cache_miss_units)},
                ):
                    for unit in cache_miss_units:
                        unit_output = cast(InterpreterOutput, unit["interpreter_output"])
                        safe_template = cast(str, unit["template"])
                        compiled_query = cast(CompiledQueryPlan, unit["compiled_query"])
                        intent_cache_service.set(
                            db=db,
                            tenant_id=scope.tenant_id,
                            intent_hash=unit_output.intent_hash,
                            normalized_intent=unit_output.intent.normalized(),
                            response_template=safe_template,
                            compiled_query=compiled_query.model_dump(mode="json"),
                        )
            else:
                # Emit skipped event if cache hit
                pipeline_monitor.emit_stage_event(
                    pipeline_id=pipeline_id,
                    stage_name="cache_storage",
                    stage_index=11,
                    status="skipped",
                    metadata={"reason": "cache_hit"},
                )

            # Stage 12: Store assistant message in history
            with self._track_stage(pipeline_id, "history_assistant_message", 12):
                history_service.append(
                    scope.tenant_id,
                    scope.user_id,
                    scope.session_id,
                    "assistant",
                    final_response,
                )

            # Stage 13: Audit logging
            with self._track_stage(pipeline_id, "audit_logging", 13):
                self._enqueue_audit_event(
                    scope=scope,
                    query_text=query_text,
                    intent_hash=interpreter_output.intent_hash,
                    domains_accessed=domains,
                    was_blocked=False,
                    block_reason=None,
                    response_summary=final_response,
                    latency_ms=latency_ms,
                )

            # Emit pipeline completion
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id, status="success", total_duration_ms=latency_ms
            )

            primary_compiled_query = cast(
                CompiledQueryPlan,
                execution_units[0]["compiled_query"],
            )
            response_source = (
                "multi_domain"
                if len(execution_units) > 1
                else primary_compiled_query.source_type
            )

            return PipelineResult(
                response_text=final_response,
                source=response_source,
                latency_ms=latency_ms,
                intent_hash=intent_hash,
                domains_accessed=domains,
                policy_proof_ids=policy_proof_ids,
                was_blocked=False,
            )

        except ZTAError as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            fallback_hash = intent_hash or "0" * 64

            # Still log audit even on error
            with self._track_stage(pipeline_id, "audit_logging_error", 12):
                self._enqueue_audit_event(
                    scope=scope,
                    query_text=query_text,
                    intent_hash=fallback_hash,
                    domains_accessed=domains,
                    was_blocked=True,
                    block_reason=exc.code,
                    response_summary=exc.message,
                    latency_ms=latency_ms,
                )

            # Emit pipeline failure
            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id,
                status="error",
                total_duration_ms=latency_ms,
                final_message=exc.message,
            )

            raise

        except Exception as exc:  # noqa: BLE001
            latency_ms = int((time.perf_counter() - started) * 1000)
            fallback_hash = intent_hash or "0" * 64

            with self._track_stage(pipeline_id, "audit_logging_error", 12):
                self._enqueue_audit_event(
                    scope=scope,
                    query_text=query_text,
                    intent_hash=fallback_hash,
                    domains_accessed=domains,
                    was_blocked=True,
                    block_reason="UNEXPECTED_ERROR",
                    response_summary=str(exc),
                    latency_ms=latency_ms,
                )

            pipeline_monitor.emit_pipeline_complete(
                pipeline_id=pipeline_id,
                status="error",
                total_duration_ms=latency_ms,
                final_message=str(exc),
            )
            raise


pipeline_service = PipelineService()
