from __future__ import annotations

from app.compiler.detokenizer import detokenizer
from app.compiler.query_builder import query_builder
from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, ScopeContext


class CompilerService:
    def compile_intent(
        self, scope: ScopeContext, intent: InterpretedIntent
    ) -> CompiledQueryPlan:
        return query_builder.build(scope, intent)

    def detokenize(
        self,
        template: str,
        query_plan: CompiledQueryPlan,
        values: dict[str, object],
        masked_fields_applied: list[str] | None = None,
    ) -> str:
        return detokenizer.fill_slots(
            template, query_plan, values, masked_fields_applied
        )


compiler_service = CompilerService()
