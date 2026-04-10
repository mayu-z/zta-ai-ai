from __future__ import annotations

from sqlalchemy.orm import Session

from app.compiler.detokenizer import detokenizer
from app.compiler.query_builder import query_builder
from app.schemas.pipeline import CompiledQueryPlan, InterpretedIntent, ScopeContext


class CompilerService:
    def compile_intent(
        self,
        scope: ScopeContext,
        intent: InterpretedIntent,
        db: Session | None = None,
    ) -> CompiledQueryPlan:
        return query_builder.build(scope, intent, db)

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
