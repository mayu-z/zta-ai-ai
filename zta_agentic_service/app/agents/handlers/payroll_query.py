from __future__ import annotations

from typing import Any

from app.agents.base_handler import AgentContext, AgentResult, BaseAgentHandler


class PayrollQueryHandler(BaseAgentHandler):
    """Read-only payroll responder with fail-closed monitor prerequisite enforcement."""

    def __init__(self, llm_gateway: Any | None = None, instance_store: Any | None = None) -> None:
        self.llm_gateway = llm_gateway
        self.instance_store = instance_store

    @property
    def is_side_effect(self) -> bool:
        return False

    async def execute(self, ctx: AgentContext) -> AgentResult:
        monitor_active = await self._monitor_active(ctx)
        if not monitor_active:
            return AgentResult(
                status="failed",
                output={},
                error=(
                    "Payroll queries require the Sensitive Field Access Monitor to be active. "
                    "Enable sensitive_field_monitor_v1 for this tenant first."
                ),
            )

        response = await self._render_response(
            template=(ctx.instance.config or {}).get("response_template", "payroll_summary"),
            slots=ctx.claim_set,
        )

        return AgentResult(
            status="success",
            output={
                "response": response,
                "payslip_available": ctx.claim_set.get("payslip_available", False),
                "pay_period": ctx.claim_set.get("pay_period"),
            },
        )

    async def rollback(self, ctx: AgentContext, partial_result: AgentResult) -> None:
        _ = (ctx, partial_result)

    def validate_config(self, config: dict[str, Any]) -> list[str]:
        _ = config
        return []

    async def _monitor_active(self, ctx: AgentContext) -> bool:
        if self.instance_store and hasattr(self.instance_store, "is_active"):
            result = self.instance_store.is_active(
                template_id="sensitive_field_monitor_v1",
                tenant_id=ctx.tenant_id,
            )
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)
        # Fail closed if monitor dependency is unavailable.
        return False

    async def _render_response(self, template: str, slots: dict[str, Any]) -> str:
        if self.llm_gateway and hasattr(self.llm_gateway, "fill_template"):
            result = await self.llm_gateway.fill_template(template=template, slots=slots)
            if isinstance(result, dict):
                return str(result.get("text") or result.get("body") or "")
            return str(getattr(result, "text", ""))

        period = slots.get("pay_period", "current period")
        gross = slots.get("gross_salary", "N/A")
        net = slots.get("net_salary", "N/A")
        return f"Payroll summary for {period}: gross={gross}, net={net}."
